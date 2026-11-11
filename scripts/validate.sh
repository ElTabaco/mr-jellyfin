#!/usr/bin/env bash
# Static validation of the repository. No cluster access, nothing is applied.
#
# Usage:   scripts/validate.sh
# Env:     K8S_VERSION  Kubernetes version for schema validation (default 1.37.2 = cluster version)
#          STRICT=1     production values must render completely (no PENDING values); use before deploy
#          PYTHON       Python interpreter with PyYAML (default python3)
# Needs:   helm, kubeconform, PyYAML. Optional, skipped with a notice if missing:
#          promtool, yamllint and the shell linter (shellcheck).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CHART="$ROOT/kubernetes/chart"
K8S_VERSION="${K8S_VERSION:-1.37.2}"
STRICT="${STRICT:-0}"
PYTHON="${PYTHON:-python3}"
OUT="$(mktemp -d)"
trap 'rm -rf "$OUT"' EXIT

failures=0
pass() { echo "  PASS  $*"; }
warn() { echo "  WARN  $*"; }
bad() {
    echo "  FAIL  $*"
    failures=$((failures + 1))
}
step() { echo "==> $*"; }
have() { command -v "$1" > /dev/null 2>&1; }

for tool in helm kubeconform; do
    have "$tool" || {
        echo "missing required tool: $tool"
        exit 2
    }
done
"$PYTHON" -c 'import yaml' 2> /dev/null || {
    echo "missing PyYAML for $PYTHON"
    exit 2
}

KC=(kubeconform -strict -summary -kubernetes-version "$K8S_VERSION"
    -schema-location default
    -schema-location 'https://raw.githubusercontent.com/datreeio/CRDs-catalog/main/{{.Group}}/{{.ResourceKind}}_{{.ResourceAPIVersion}}.json')

step "helm lint (test values)"
if helm lint "$CHART" -f "$CHART/values.yaml" -f "$CHART/ci/test-values.yaml" > "$OUT/lint.txt" 2>&1; then
    pass "helm lint"
else
    cat "$OUT/lint.txt"
    bad "helm lint"
fi

step "helm template (test values: every optional feature on)"
if helm template mr-do-jellyfin "$CHART" -n mr-do-jellyfin -f "$CHART/ci/test-values.yaml" > "$OUT/ci.yaml" 2> "$OUT/ci.err"; then
    pass "render test values ($(grep -c '^kind:' "$OUT/ci.yaml") objects)"
else
    cat "$OUT/ci.err"
    bad "render test values"
fi

step "helm template (production values)"
PROD_RENDERED=0
if helm template mr-do-jellyfin "$CHART" -n mr-do-jellyfin -f "$CHART/values-production.yaml" > "$OUT/prod.yaml" 2> "$OUT/prod.err"; then
    pass "render production values ($(grep -c '^kind:' "$OUT/prod.yaml") objects)"
    PROD_RENDERED=1
elif grep -q 'PENDING(' "$OUT/prod.err" && [ "$STRICT" != "1" ]; then
    warn "production values incomplete: $(grep -o 'PENDING([^)]*): [^"]*' "$OUT/prod.err" | head -1)"
else
    cat "$OUT/prod.err"
    bad "render production values"
fi

step "kubeconform (Kubernetes $K8S_VERSION schemas)"
manifests=("$OUT/ci.yaml" "$ROOT/kubernetes/application.yaml"
    "$ROOT/kubernetes/platform/gpu-device-plugin/application.yaml"
    "$ROOT/kubernetes/platform/gpu-device-plugin/manifests")
[ "$PROD_RENDERED" = "1" ] && manifests+=("$OUT/prod.yaml")
if "${KC[@]}" "${manifests[@]}"; then
    pass "kubeconform"
else
    bad "kubeconform"
fi

step "policy checks (images pinned, storage retained, no privileged pods)"
policy_inputs=("$OUT/ci.yaml" "$ROOT/kubernetes/platform/gpu-device-plugin/manifests/daemonset.yaml")
[ "$PROD_RENDERED" = "1" ] && policy_inputs+=("$OUT/prod.yaml")
if "$PYTHON" "$ROOT/scripts/policy_check.py" "${policy_inputs[@]}"; then
    pass "policy checks"
else
    bad "policy checks"
fi

step "monitoring rules"
if have promtool; then
    if promtool check rules "$ROOT/monitoring/alerts.yaml" && (cd "$ROOT/monitoring" && promtool test rules alerts.test.yaml); then
        pass "promtool check + unit tests"
    else
        bad "promtool"
    fi
else
    warn "promtool not installed, rules not checked"
fi

step "scripts"
mapfile -t shell_scripts < <(find "$ROOT/scripts" "$ROOT/kubernetes" -name '*.sh' -type f | sort)
for script in "${shell_scripts[@]}"; do
    bash -n "$script" || bad "bash -n $script"
done
if have shellcheck; then
    if shellcheck -x "${shell_scripts[@]}"; then pass "shellcheck (${#shell_scripts[@]} files)"; else bad "shellcheck"; fi
else
    warn "shellcheck not installed, only bash -n run"
fi
if "$PYTHON" -m py_compile "$CHART/files/backup.py" "$ROOT/scripts/policy_check.py" "$ROOT/scripts/configure-transcoding.py" "$ROOT/scripts/configure-livetv.py" "$ROOT/scripts/check-livetv.py" "$ROOT/scripts/loadtest/loadtest.py" "$ROOT/scripts/loadtest/analyze.py"; then
    pass "python compile"
else
    bad "python compile"
fi

step "yamllint"
if have yamllint; then
    if yamllint -c "$ROOT/.yamllint" "$ROOT"; then pass "yamllint"; else bad "yamllint"; fi
else
    warn "yamllint not installed"
fi

step "secret scan"
if bash "$ROOT/scripts/check-no-secrets.sh" "$ROOT"; then pass "no secrets"; else bad "secret scan"; fi

echo
if [ "$failures" -eq 0 ]; then
    echo "VALIDATION PASSED"
else
    echo "VALIDATION FAILED: $failures check(s)"
    exit 1
fi
