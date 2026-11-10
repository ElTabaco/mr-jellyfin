#!/usr/bin/env bash
# Health check of the Jellyfin deployment. Read-only.
#
# Usage:   scripts/healthcheck.sh                 HTTP checks only (any LAN host)
#          WITH_KUBECTL=1 scripts/healthcheck.sh  plus Kubernetes/Argo CD state (on mr0)
# Env:     JELLYFIN_URL (http://192.168.0.5:8096), NAMESPACE (mr-do-jellyfin), RELEASE (mr-do-jellyfin)
set -uo pipefail

JELLYFIN_URL="${JELLYFIN_URL:-http://192.168.0.5:8096}"
NAMESPACE="${NAMESPACE:-mr-do-jellyfin}"
RELEASE="${RELEASE:-mr-do-jellyfin}"
failures=0

check() {
    local name="$1"
    shift
    if "$@" > /dev/null 2>&1; then
        echo "  OK    $name"
    else
        echo "  FAIL  $name"
        failures=$((failures + 1))
    fi
}

echo "== HTTP ($JELLYFIN_URL)"
check "/health returns 200" curl -fsS --max-time 10 "$JELLYFIN_URL/health"
check "/System/Info/Public" curl -fsS --max-time 10 "$JELLYFIN_URL/System/Info/Public"
version="$(curl -fsS --max-time 10 "$JELLYFIN_URL/System/Info/Public" 2> /dev/null |
    python3 -c 'import json,sys; print(json.load(sys.stdin).get("Version",""))' 2> /dev/null)"
echo "        server version: ${version:-unknown}"
check "/metrics exposed" curl -fsS --max-time 10 "$JELLYFIN_URL/metrics"

if [ "${WITH_KUBECTL:-0}" = "1" ]; then
    echo "== Kubernetes ($NAMESPACE)"
    check "deployment available" kubectl -n "$NAMESPACE" rollout status deployment "$RELEASE" --timeout=10s
    for pvc in config cache media backup; do
        phase="$(kubectl -n "$NAMESPACE" get pvc "${RELEASE}-pvc-$pvc" -o jsonpath='{.status.phase}' 2> /dev/null)"
        check "pvc $pvc Bound (${phase:-missing})" test "$phase" = "Bound"
    done
    restarts="$(kubectl -n "$NAMESPACE" get pods -l "app=$RELEASE" -o jsonpath='{range .items[*].status.containerStatuses[*]}{.restartCount}{"\n"}{end}' | awk '{s+=$1} END {print s+0}')"
    echo "        container restarts: $restarts"
    sync="$(kubectl -n argocd get application "$RELEASE" -o jsonpath='{.status.sync.status}/{.status.health.status}' 2> /dev/null)"
    check "argo cd Synced/Healthy (${sync:-missing})" test "$sync" = "Synced/Healthy"
    last="$(kubectl -n "$NAMESPACE" get cronjob "${RELEASE}-backup" -o jsonpath='{.status.lastSuccessfulTime}' 2> /dev/null)"
    echo "        last successful backup: ${last:-never}"
fi

if [ "$failures" -eq 0 ]; then
    echo "HEALTHY"
else
    echo "UNHEALTHY: $failures check(s) failed"
    exit 1
fi
