#!/usr/bin/env bash
# Run a Jellyfin backup now (e.g. before an upgrade) and wait for the result.
# Creates a Job from the backup CronJob, so it uses exactly the deployed backup code.
#
# Usage:   scripts/backup.sh            (run where kubectl talks to the cluster, e.g. mr0)
# Env:     NAMESPACE (mr-do-jellyfin), CRONJOB (mr-do-jellyfin-backup), TIMEOUT_SECONDS (3600)
set -euo pipefail

NAMESPACE="${NAMESPACE:-mr-do-jellyfin}"
CRONJOB="${CRONJOB:-mr-do-jellyfin-backup}"
TIMEOUT_SECONDS="${TIMEOUT_SECONDS:-3600}"
JOB="${CRONJOB}-manual-$(date +%Y%m%d%H%M%S)"

kubectl -n "$NAMESPACE" get cronjob "$CRONJOB" > /dev/null
kubectl -n "$NAMESPACE" create job --from="cronjob/$CRONJOB" "$JOB"
echo "waiting for job/$JOB (max ${TIMEOUT_SECONDS}s)"

deadline=$((SECONDS + TIMEOUT_SECONDS))
result=""
while [ "$SECONDS" -lt "$deadline" ]; do
    succeeded="$(kubectl -n "$NAMESPACE" get job "$JOB" -o jsonpath='{.status.succeeded}')"
    failed="$(kubectl -n "$NAMESPACE" get job "$JOB" -o jsonpath='{.status.failed}')"
    if [ "${succeeded:-0}" -ge 1 ]; then
        result="ok"
        break
    fi
    if [ "${failed:-0}" -ge 1 ] && [ -z "$(kubectl -n "$NAMESPACE" get pods -l job-name="$JOB" --field-selector=status.phase=Running -o name)" ]; then
        result="failed"
        break
    fi
    sleep 10
done

kubectl -n "$NAMESPACE" logs "job/$JOB" --all-containers --tail=200 || true

case "$result" in
    ok) echo "BACKUP OK: job/$JOB" ;;
    failed)
        echo "BACKUP FAILED: job/$JOB" >&2
        exit 1
        ;;
    *)
        echo "BACKUP TIMEOUT: job/$JOB did not finish in ${TIMEOUT_SECONDS}s" >&2
        exit 1
        ;;
esac
