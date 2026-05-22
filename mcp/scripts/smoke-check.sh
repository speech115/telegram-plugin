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
  ensure_python_runtime
  printf 'Running telegram-mcp daemon facade smoke via direct MCP client...\n'
  TELEGRAM_MCP_HOST="${HOST}" \
  TELEGRAM_MCP_PORT="${PORT}" \
  TELEGRAM_MCP_HTTP_PATH="${HTTP_PATH}" \
  PYTHONPATH="${PYTHONPATH_VALUE}" \
  "${PYTHON_BIN}" <<'PY'
import asyncio
import json
import os
from datetime import timedelta

import httpx
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client


def _tool_payload(result):
    structured = getattr(result, "structuredContent", None)
    if isinstance(structured, dict):
        return structured
    for item in getattr(result, "content", []) or []:
        text = getattr(item, "text", None)
        if not text:
            continue
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    return {}


async def main():
    token = os.environ.get("TELEGRAM_MCP_AUTH_TOKEN", "").strip()
    if not token:
        raise SystemExit("TELEGRAM_MCP_AUTH_TOKEN is required for daemon facade smoke")
    host = os.environ.get("TELEGRAM_MCP_HOST", "127.0.0.1")
    port = os.environ.get("TELEGRAM_MCP_PORT", "8799")
    path = os.environ.get("TELEGRAM_MCP_HTTP_PATH", "/mcp")
    endpoint = f"http://{host}:{port}{path}"
    read_timeout = timedelta(seconds=30)

    async with httpx.AsyncClient(headers={"Authorization": f"Bearer {token}"}) as http_client:
        async with streamable_http_client(endpoint, http_client=http_client) as (read_stream, write_stream, _):
            async with ClientSession(read_stream, write_stream, read_timeout_seconds=read_timeout) as session:
                await session.initialize()
                resolved = await session.call_tool(
                    "resolve_dialog",
                    {"query": "me"},
                    read_timeout_seconds=read_timeout,
                )
                if resolved.isError:
                    raise SystemExit("resolve_dialog returned isError=true")
                dialog_ref = _tool_payload(resolved).get("dialog_ref") or _tool_payload(resolved).get("id")
                if dialog_ref is None:
                    raise SystemExit("resolve_dialog did not return dialog_ref")
                collected = await session.call_tool(
                    "collect_dialog_context",
                    {
                        "chat": str(dialog_ref),
                        "mode": "fast",
                        "recent_limit": 1,
                        "include_pinned": False,
                    },
                    read_timeout_seconds=read_timeout,
                )
                if collected.isError:
                    raise SystemExit("collect_dialog_context returned isError=true")
                print("Facade smoke direct MCP client passed.")


asyncio.run(main())
PY
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
