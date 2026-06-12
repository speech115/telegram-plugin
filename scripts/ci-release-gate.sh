#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export TELEGRAM_MONOREPO_ROOT="${ROOT}"
export TELEGRAM_CONTROL_PLANE_ROOT="${ROOT}/control-plane"
export TELEGRAM_MCP_REPO="${ROOT}/mcp"
export TELEGRAM_PLUGIN_SOURCE="${ROOT}/plugin"
export TELEGRAM_PLUGIN_PACKAGE="${ROOT}/plugin"
export TELEGRAM_PROJECTS_ROOT="${ROOT}"
export TELEGRAM_API_ID="${TELEGRAM_API_ID:-1}"
export TELEGRAM_API_HASH="${TELEGRAM_API_HASH:-hash}"

failures=0

run_gate() {
  local name="$1"
  shift
  if "$@"; then
    printf 'ci-release-gate: %s ok\n' "${name}"
  else
    printf 'ci-release-gate: %s failed\n' "${name}" >&2
    failures=$((failures + 1))
  fi
}

PYTHON_BIN="${ROOT}/mcp/.venv/bin/python"
if [[ ! -x "${PYTHON_BIN}" ]]; then
  python3 -m venv "${ROOT}/mcp/.venv"
fi
"${PYTHON_BIN}" -m pip install -q --upgrade pip
"${PYTHON_BIN}" -m pip install -q -e "${ROOT}/mcp" pytest pyyaml

find "${ROOT}/mcp/src" "${ROOT}/control-plane/src" -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true

run_gate packaging-hygiene "${ROOT}/scripts/packaging-hygiene.sh" \
  "${ROOT}/plugin" \
  "${ROOT}/control-plane/src" \
  "${ROOT}/control-plane/bin" \
  "${ROOT}/mcp/src"

run_gate mcp-pytest bash -lc "cd '${ROOT}/mcp' && '${PYTHON_BIN}' -m pytest -q --ignore=tests/test_ops_scripts.py"

run_gate mcp-release-gates bash -lc \
  "cd '${ROOT}/mcp' && PYTHONPATH='${ROOT}/mcp/src' '${PYTHON_BIN}' -m telegram_mcp.release_gates --package-dir '${ROOT}/plugin' --json"

run_gate plugin-package-build bash -lc "
  tmp=\$(mktemp -d)
  '${ROOT}/mcp/bin/build-plugin-package' \
    --source-dir '${ROOT}/plugin' \
    --output-dir \"\${tmp}/out\" \
    --json >/dev/null
  test -f \"\${tmp}/out/.codex-plugin/plugin.json\"
"

CP_ENV="TELEGRAM_CI_PORTABLE=1 TELEGRAM_MONOREPO_ROOT='${ROOT}' TELEGRAM_CONTROL_PLANE_ROOT='${ROOT}/control-plane' TELEGRAM_MCP_REPO='${ROOT}/mcp' TELEGRAM_PLUGIN_SOURCE='${ROOT}/plugin' TELEGRAM_PLUGIN_PACKAGE='${ROOT}/plugin' TELEGRAM_PROJECTS_ROOT='${ROOT}' PYTHONPATH='${ROOT}/control-plane/src:${ROOT}/mcp/src'"

run_gate control-plane-pytest bash -lc "cd '${ROOT}/control-plane' && ${CP_ENV} '${PYTHON_BIN}' -m pytest -q"

run_gate managed-systems bash -lc \
  "${CP_ENV} '${PYTHON_BIN}' -m telegram_control_plane managed-systems --json | '${PYTHON_BIN}' -c \"import json,sys; d=json.load(sys.stdin); sys.exit(0 if d.get('status') in ('ok','warn') else 1)\""

run_gate mcp-surface bash -lc \
  "${CP_ENV} '${PYTHON_BIN}' -m telegram_control_plane mcp-surface --json | '${PYTHON_BIN}' -c \"import json,sys; d=json.load(sys.stdin); sys.exit(0 if d.get('status')=='ok' else 1)\""

run_gate docs-audit bash -lc \
  "${CP_ENV} '${PYTHON_BIN}' -m telegram_control_plane docs-audit --json | '${PYTHON_BIN}' -c \"import json,sys; d=json.load(sys.stdin); sys.exit(0 if d.get('status')=='ok' else 1)\""

run_gate release-gates bash -lc \
  "${CP_ENV} '${PYTHON_BIN}' -m telegram_control_plane release-gates --json | '${PYTHON_BIN}' -c \"import json,sys; d=json.load(sys.stdin); sys.exit(0 if d.get('status')=='ok' else 1)\""

run_gate install-adapters bash -lc \
  "${CP_ENV} '${PYTHON_BIN}' -m telegram_control_plane install-adapters --json | '${PYTHON_BIN}' -c \"import json,sys; d=json.load(sys.stdin); sys.exit(0 if d.get('status')=='ok' else 1)\""

if [[ "${failures}" -gt 0 ]]; then
  printf 'ci-release-gate: %s check(s) failed\n' "${failures}" >&2
  exit 1
fi

printf 'ci-release-gate: all checks passed\n'
