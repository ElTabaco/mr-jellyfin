#!/bin/bash
# Register the mr-do-jellyfin Argo CD Application. Argo CD then reconciles the Helm chart
# in kubernetes/chart from Git. Run on mr0 (kubectl host). Run from anywhere: the script
# self-locates.
#
#   kubernetes/apply.sh          Jellyfin application only
#   kubernetes/apply.sh --gpu    also the GPU device plugin application (Phase 4)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ "${1:-}" = "--gpu" ]; then
    kubectl apply -f "$SCRIPT_DIR/platform/gpu-device-plugin/application.yaml"
fi
kubectl apply -f "$SCRIPT_DIR/application.yaml"

# ── Verification (non-fatal) ──
echo ""
echo "=== ArgoCD Applications ==="
kubectl get applications -n argocd | grep -E 'NAME|mr-do-jellyfin' || true

echo ""
echo "=== Pods ==="
kubectl get pods -n mr-do-jellyfin -o wide || true

echo ""
echo "=== Service ==="
kubectl get svc -n mr-do-jellyfin || true

echo ""
echo "=== PVC / PV ==="
kubectl get pvc -n mr-do-jellyfin || true
kubectl get pv | grep -E 'NAME|mr-do-jellyfin' || true
