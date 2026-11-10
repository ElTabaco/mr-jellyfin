#!/usr/bin/env bash
# Restore Jellyfin from a backup on the backup volume. Destructive for the running state:
# the current state is moved to /config/.pre-restore-<stamp>/ (kept, not deleted).
#
# Usage (where kubectl talks to the cluster, e.g. mr0):
#   scripts/restore.sh --list                         list backups on the backup volume
#   scripts/restore.sh --files <jellyfin-files-*.tar.gz>
#       Stops Jellyfin, restores database + config + plugins + library definitions, starts it.
#   scripts/restore.sh --stage-api <jellyfin-backup-*.zip>
#       Copies a Jellyfin API archive into /config/data/backups; then restore it in the
#       Jellyfin dashboard (Administration > Backups) or via POST /Backup/Restore.
#
# Argo CD self-heal would scale Jellyfin back up, so --files suspends automated sync of the
# application for the restore and re-enables it afterwards (also on failure).
# Env: NAMESPACE (mr-do-jellyfin), RELEASE (mr-do-jellyfin), ARGO_APP (mr-do-jellyfin)
set -euo pipefail

NAMESPACE="${NAMESPACE:-mr-do-jellyfin}"
RELEASE="${RELEASE:-mr-do-jellyfin}"
ARGO_APP="${ARGO_APP:-mr-do-jellyfin}"
POD="${RELEASE}-restore-$(date +%Y%m%d%H%M%S)"

usage() {
    sed -n '2,16p' "$0"
    exit 2
}

[ $# -ge 1 ] || usage
MODE="$1"
ARCHIVE="${2:-}"

# Image + UID come from the deployed backup CronJob (same pinned image as the backups).
IMAGE="$(kubectl -n "$NAMESPACE" get cronjob "${RELEASE}-backup" -o jsonpath='{.spec.jobTemplate.spec.template.spec.containers[0].image}')"
UID_="$(kubectl -n "$NAMESPACE" get cronjob "${RELEASE}-backup" -o jsonpath='{.spec.jobTemplate.spec.template.spec.securityContext.runAsUser}')"
GID_="$(kubectl -n "$NAMESPACE" get cronjob "${RELEASE}-backup" -o jsonpath='{.spec.jobTemplate.spec.template.spec.securityContext.runAsGroup}')"
NODE_SELECTOR="$(kubectl -n "$NAMESPACE" get cronjob "${RELEASE}-backup" -o jsonpath='{.spec.jobTemplate.spec.template.spec.nodeSelector}')"
[ -n "$NODE_SELECTOR" ] || NODE_SELECTOR='{}'

# run_pod <restore-mode> <command...>: one-off pod with config + backup volumes (PSA restricted).
run_pod() {
    local restore_mode="$1"
    shift
    local cmd_json
    cmd_json="$(printf '%s\n' "$@" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read().splitlines()))')"
    kubectl -n "$NAMESPACE" run "$POD" --rm -i --restart=Never --quiet --image="$IMAGE" --overrides "$(
        cat << EOF
{
  "apiVersion": "v1",
  "spec": {
    "nodeSelector": $NODE_SELECTOR,
    "automountServiceAccountToken": false,
    "securityContext": {"runAsNonRoot": true, "runAsUser": $UID_, "runAsGroup": $GID_,
                        "seccompProfile": {"type": "RuntimeDefault"}},
    "containers": [{
      "name": "$POD",
      "image": "$IMAGE",
      "command": $cmd_json,
      "env": [{"name": "ARCHIVE", "value": "$ARCHIVE"}, {"name": "MODE", "value": "$restore_mode"}],
      "securityContext": {"allowPrivilegeEscalation": false, "readOnlyRootFilesystem": true,
                          "capabilities": {"drop": ["ALL"]}},
      "volumeMounts": [{"name": "scripts", "mountPath": "/scripts", "readOnly": true},
                       {"name": "config", "mountPath": "/config"},
                       {"name": "backup", "mountPath": "/backup"}]
    }],
    "volumes": [{"name": "scripts", "configMap": {"name": "${RELEASE}-scripts", "defaultMode": 365}},
                {"name": "config", "persistentVolumeClaim": {"claimName": "${RELEASE}-pvc-config"}},
                {"name": "backup", "persistentVolumeClaim": {"claimName": "${RELEASE}-pvc-backup"}}]
  }
}
EOF
    )"
}

resume_argo() {
    echo "re-enabling Argo CD automated sync for $ARGO_APP"
    kubectl -n argocd patch application "$ARGO_APP" --type merge \
        -p '{"spec":{"syncPolicy":{"automated":{"prune":true,"selfHeal":true}}}}'
}

case "$MODE" in
    --list)
        # shellcheck disable=SC2016  # expanded inside the pod, not here
        run_pod list sh -c 'for d in /backup/files /backup/api; do echo "== $d"; ls -l "$d" 2>/dev/null | grep -v sha256; done'
        ;;
    --stage-api)
        [ -n "$ARCHIVE" ] || usage
        run_pod stage-api python3 /scripts/restore.py
        ;;
    --files)
        [ -n "$ARCHIVE" ] || usage
        echo "This stops Jellyfin and replaces its database/config with $ARCHIVE."
        read -r -p "Type RESTORE to continue: " answer
        [ "$answer" = "RESTORE" ] || {
            echo "aborted"
            exit 1
        }
        kubectl -n argocd patch application "$ARGO_APP" --type merge -p '{"spec":{"syncPolicy":{"automated":null}}}'
        trap resume_argo EXIT
        kubectl -n "$NAMESPACE" scale deployment "$RELEASE" --replicas=0
        for _ in $(seq 1 36); do
            [ -z "$(kubectl -n "$NAMESPACE" get pods -l "app=$RELEASE" -o name)" ] && break
            sleep 5
        done
        if [ -n "$(kubectl -n "$NAMESPACE" get pods -l "app=$RELEASE" -o name)" ]; then
            echo "Jellyfin pod still running after 180s, aborting" >&2
            exit 1
        fi
        run_pod files python3 /scripts/restore.py
        kubectl -n "$NAMESPACE" scale deployment "$RELEASE" --replicas=1
        kubectl -n "$NAMESPACE" rollout status deployment "$RELEASE" --timeout=900s
        echo "RESTORE OK. Verify: scripts/healthcheck.sh, log in, check libraries and users."
        ;;
    *) usage ;;
esac
