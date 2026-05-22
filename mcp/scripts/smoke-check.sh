#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PYTHON_BIN="${PROJECT_ROOT}/.venv/bin/python"
PYTHONPATH_VALUE="${PROJECT_ROOT}/src"

TRANSPORT="${TELEGRAM_MCP_TRANSPORT:-streamable-http}"
HOST="${TELEGRAM_MCP_HOST:-127.0.0.1}"
PORT="${TELEGRAM_MCP_PORT:-8799}"
HTTP_PATH="${TELEGRAM_MCP_HTTP_PATH:-/mcp}"
MCPORTER_BIN="${MCPORTER_BIN:-$(command -v mcporter || true)}"

cd "${PROJECT_ROOT}"

ensure_python_runtime() {
  if [ -x "${PYTHON_BIN}" ]; then
    return 0
  fi
  printf 'Missing repo-local python at %s.\n' "${PYTHON_BIN}" >&2
  printf 'Bootstrap the local virtualenv with: uv pip install -e .\n' >&2
  exit 1
}

ensure_mcporter_runtime() {
  if [ -n "${MCPORTER_BIN}" ]; then
    return 0
  fi
  printf 'Missing mcporter in PATH for %s daemon checks.\n' "${TRANSPORT}" >&2
  printf 'Install mcporter or rerun with TELEGRAM_MCP_TRANSPORT=stdio for direct Python diagnostics.\n' >&2
  exit 1
}

run_python_check() {
  local command_name="$1"
  local display_name="$2"

  printf 'Running telegram-mcp %s...\n' "${command_name}"
  set +e
  TELEGRAM_MCP_TRANSPORT="${TRANSPORT}" \
  TELEGRAM_MCP_HOST="${HOST}" \
  TELEGRAM_MCP_PORT="${PORT}" \
  TELEGRAM_MCP_HTTP_PATH="${HTTP_PATH}" \
  PYTHONPATH="${PYTHONPATH_VALUE}" \
  "${PYTHON_BIN}" - "${command_name}" <<'PY'
from telegram_mcp.auth import run_doctor, run_health
import sys

{"health": run_health, "doctor": run_doctor}[sys.argv[1]]()
PY
  local exit_code=$?
  set -e
  if [ "${exit_code}" -ne 0 ]; then
    printf '%s check failed with exit code %s.\n' "${display_name}" "${exit_code}" >&2
    exit "${exit_code}"
  fi
}

run_daemon_health_check() {
  printf 'Running telegram-mcp daemon health via mcporter...\n'
  if ! "${MCPORTER_BIN}" call telegram.get_me --timeout 30000 --output json >/dev/null; then
    printf 'Health check failed: mcporter call telegram.get_me returned non-zero.\n' >&2
    exit 1
  fi
}

run_daemon_doctor_check() {
  printf 'Running telegram-mcp daemon doctor via mcporter...\n'
  if ! "${MCPORTER_BIN}" list telegram --json >/dev/null; then
    printf 'Doctor check failed: mcporter list telegram returned non-zero.\n' >&2
    exit 1
  fi
  if ! "${MCPORTER_BIN}" call telegram.get_me --timeout 30000 --output json >/dev/null; then
    printf 'Doctor check failed: mcporter call telegram.get_me returned non-zero.\n' >&2
    exit 1
  fi
}

extract_dialog_ref() {
  python3 -c 'import json, sys
try:
    payload = json.load(sys.stdin)
except json.JSONDecodeError:
    sys.exit(2)
dialog_ref = payload.get("dialog_ref") or payload.get("id")
if dialog_ref is None:
    sys.exit(4)
print(dialog_ref)'
}

run_daemon_facade_smoke_check() {
  local dialog_payload
  local dialog_ref

  printf 'Running telegram-mcp daemon facade smoke via mcporter...\n'
  dialog_payload="$("${MCPORTER_BIN}" call telegram.resolve_dialog query=me --output json)" || {
    printf 'Facade smoke check failed: mcporter call telegram.resolve_dialog returned non-zero.\n' >&2
    exit 1
  }

  dialog_ref="$(printf '%s' "${dialog_payload}" | extract_dialog_ref)" || {
    printf 'Facade smoke check failed: could not extract a dialog ref from telegram.resolve_dialog.\n' >&2
    exit 1
  }

  printf 'Facade smoke dialog ref: %s\n' "${dialog_ref}"
  if ! "${MCPORTER_BIN}" call telegram.collect_dialog_context chat="${dialog_ref}" mode=fast recent_limit=1 include_pinned=false --output json >/dev/null; then
    printf 'Facade smoke check failed: mcporter call telegram.collect_dialog_context returned non-zero.\n' >&2
    exit 1
  fi
}

if [ "${TRANSPORT}" != "stdio" ]; then
  ensure_mcporter_runtime
  run_daemon_health_check

  printf '\n'
  run_daemon_doctor_check

  printf '\n'
  run_daemon_facade_smoke_check
else
  ensure_python_runtime
  run_python_check "health" "Health"

  printf '\n'
  run_python_check "doctor" "Doctor"
fi

if [ "${TRANSPORT}" != "stdio" ]; then
  printf '\nChecking listener on %s:%s...\n' "${HOST}" "${PORT}"
  if ! nc -z "${HOST}" "${PORT}"; then
    printf 'Listener check failed for %s:%s.\n' "${HOST}" "${PORT}" >&2
    exit 1
  fi
fi

printf '\nSmoke check passed.\n'
