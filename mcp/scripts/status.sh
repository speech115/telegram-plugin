#!/bin/bash
set -euo pipefail

LABEL="com.example.telegram-mcp-http"
LOG_PATH="${HOME}/Library/Logs/telegram-mcp/http-launchd.log"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PROJECT_ROOT}/.venv/bin/python"
PYTHONPATH_VALUE="${PROJECT_ROOT}/src"
TRANSPORT="${TELEGRAM_MCP_TRANSPORT:-streamable-http}"
HOST="${TELEGRAM_MCP_HOST:-127.0.0.1}"
PORT="${TELEGRAM_MCP_PORT:-8799}"
HTTP_PATH="${TELEGRAM_MCP_HTTP_PATH:-/mcp}"
MCPORTER_BIN="${MCPORTER_BIN:-$(command -v mcporter || true)}"
ENDPOINT_URL="http://${HOST}:${PORT}${HTTP_PATH}"

cd "${PROJECT_ROOT}"

print_bootstrap_hint() {
  printf '\n--- runtime ---\n'
  printf 'Missing repo-local python at %s.\n' "${PYTHON_BIN}"
  printf 'Bootstrap the local virtualenv with: uv pip install -e .\n'
}

print_mcporter_hint() {
  printf '\n--- runtime ---\n'
  printf 'Missing mcporter in PATH for %s daemon checks.\n' "${TRANSPORT}"
  printf 'Install mcporter or rerun with TELEGRAM_MCP_TRANSPORT=stdio for direct Python diagnostics.\n'
}

run_python_check() {
  local label="$1"
  local command_name="$2"

  printf '\n--- %s ---\n' "${label}"
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
  printf '%s exit code: %s\n' "${label}" "${exit_code}"
}

run_daemon_health_check() {
  printf '\n--- health ---\n'
  set +e
  "${MCPORTER_BIN}" call telegram.get_me --timeout 30000 --output json >/dev/null
  local exit_code=$?
  set -e

  if [ "${exit_code}" -eq 0 ]; then
    cat <<EOF
{
  "connected": true,
  "authorized": true,
  "transport": "${TRANSPORT}",
  "endpoint_url": "${ENDPOINT_URL}",
  "probe": "mcporter call telegram.get_me"
}
EOF
  else
    cat <<EOF
{
  "connected": false,
  "authorized": false,
  "transport": "${TRANSPORT}",
  "endpoint_url": "${ENDPOINT_URL}",
  "probe": "mcporter call telegram.get_me",
  "error": "mcporter daemon probe failed"
}
EOF
  fi

  printf 'health exit code: %s\n' "${exit_code}"
}

run_daemon_doctor_check() {
  local list_exit
  local call_exit
  local listener_exit
  local status="ok"
  local tool_catalog="ok"
  local tool_call="ok"
  local listener="ok"
  local connection="connected"
  local warnings='[]'

  printf '\n--- doctor ---\n'
  set +e
  "${MCPORTER_BIN}" list telegram --json >/dev/null
  list_exit=$?
  "${MCPORTER_BIN}" call telegram.get_me --timeout 30000 --output json >/dev/null
  call_exit=$?
  nc -z "${HOST}" "${PORT}" >/dev/null 2>&1
  listener_exit=$?
  set -e

  if [ "${list_exit}" -ne 0 ]; then
    status="warn"
    tool_catalog="error"
    connection="error"
    warnings='["mcporter list telegram failed"]'
  fi

  if [ "${call_exit}" -ne 0 ]; then
    status="warn"
    tool_call="error"
    connection="error"
    warnings='["mcporter daemon tool call failed"]'
  fi

  if [ "${listener_exit}" -ne 0 ]; then
    status="warn"
    listener="error"
    connection="error"
    warnings='["listener probe failed"]'
  fi

  cat <<EOF
{
  "status": "${status}",
  "transport": "${TRANSPORT}",
  "checks": {
    "listener": "${listener}",
    "tool_catalog": "${tool_catalog}",
    "tool_call": "${tool_call}",
    "connection": "${connection}"
  },
  "warnings": ${warnings},
  "endpoint_url": "${ENDPOINT_URL}",
  "probe": "mcporter"
}
EOF

  if [ "${status}" = "ok" ]; then
    printf 'doctor exit code: 0\n'
  else
    printf 'doctor exit code: 1\n'
  fi
}

launchctl print "gui/$(id -u)/${LABEL}" || true

if [ "${TRANSPORT}" != "stdio" ]; then
  if [ -n "${MCPORTER_BIN}" ]; then
    run_daemon_health_check
    run_daemon_doctor_check
  else
    print_mcporter_hint
  fi
elif [ -x "${PYTHON_BIN}" ]; then
  run_python_check "health" health
  run_python_check "doctor" doctor
else
  print_bootstrap_hint
fi

if [ -f "${LOG_PATH}" ]; then
  printf '\n--- logs ---\n'
  tail -n 40 "${LOG_PATH}"
fi
