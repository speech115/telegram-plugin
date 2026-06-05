#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PYTHON_BIN="${PROJECT_ROOT}/.venv/bin/python"
PYTHONPATH_VALUE="${PROJECT_ROOT}/src"
LAUNCHD_RUNNER="${PROJECT_ROOT}/scripts/launchd-run.sh"
PROFILE="${TELEGRAM_MCP_PROFILE:-default}"
LABEL="${TELEGRAM_MCP_LABEL:-com.sereja.telegram-mcp-http}"
PLIST_PATH="${HOME}/Library/LaunchAgents/${LABEL}.plist"
LOG_DIR="${TELEGRAM_MCP_LOG_DIR:-${HOME}/Library/Logs/telegram-mcp}"
LOG_PATH="${TELEGRAM_MCP_LOG_PATH:-${LOG_DIR}/http-launchd.log}"
LOGROTATE_LABEL="${TELEGRAM_MCP_LOGROTATE_LABEL:-${LABEL}-logrotate}"
ROTATE_PLIST="${HOME}/Library/LaunchAgents/${LOGROTATE_LABEL}.plist"
ENV_FILE="${TELEGRAM_MCP_ENV_FILE:-${PROJECT_ROOT}/.env}"

reject_unsafe_env_value() {
  local key="$1"
  local value="$2"

  case "${value}" in
    *'$('*|*'`'*|*'>'*|*'<'*|*'|'*|*';'*|*'&'*)
      printf 'Unsafe env value for %s in %s\n' "${key}" "${ENV_FILE}" >&2
      exit 1
      ;;
  esac
}

file_mode() {
  stat -c '%a' "$1" 2>/dev/null || stat -f '%OLp' "$1"
}

load_env_file() {
  local line key value

  [ -f "${ENV_FILE}" ] || return 0
  if [ ! -O "${ENV_FILE}" ]; then
    printf 'Refusing env file not owned by current user: %s\n' "${ENV_FILE}" >&2
    exit 1
  fi
  mode="$(file_mode "${ENV_FILE}")"
  if [ "${mode}" != "600" ] && [ "${mode}" != "400" ]; then
    printf 'Refusing env file with unsafe permissions: %s\n' "${ENV_FILE}" >&2
    exit 1
  fi

  while IFS= read -r line || [ -n "${line}" ]; do
    case "${line}" in
      ''|'#'*) continue ;;
      export\ *) line="${line#export }" ;;
    esac
    case "${line}" in
      *=*) ;;
      *)
        printf 'Invalid env line in %s\n' "${ENV_FILE}" >&2
        exit 1
        ;;
    esac
    key="${line%%=*}"
    value="${line#*=}"
    case "${key}" in
      TELEGRAM_[A-Z0-9_]*)
        ;;
      *)
        printf 'Unsupported env key %s in %s\n' "${key}" "${ENV_FILE}" >&2
        exit 1
        ;;
    esac
    if [ "${key}" = "TELEGRAM_MCP_TOOL_PROFILE" ]; then
      printf 'Refusing TELEGRAM_MCP_TOOL_PROFILE in default launchd env file\n' >&2
      exit 1
    fi
    reject_unsafe_env_value "${key}" "${value}"
    export "${key}=${value}"
  done < "${ENV_FILE}"
}

escape_xml() {
  local value="$1"
  value="${value//&/&amp;}"
  value="${value//</&lt;}"
  value="${value//>/&gt;}"
  value="${value//\"/&quot;}"
  value="${value//\'/&apos;}"
  printf '%s' "${value}"
}

append_xml_string() {
  local key="$1"
  local value="$2"
  printf '    <key>%s</key>\n' "$(escape_xml "${key}")" >> "${PLIST_PATH}"
  printf '    <string>%s</string>\n' "$(escape_xml "${value}")" >> "${PLIST_PATH}"
}

# Parse env file for Telegram credentials without evaluating shell syntax.
if [ -f "${ENV_FILE}" ]; then
    load_env_file
fi

TRANSPORT="${TELEGRAM_MCP_TRANSPORT:-streamable-http}"
HOST="${TELEGRAM_MCP_HOST:-127.0.0.1}"
PORT="${TELEGRAM_MCP_PORT:-8799}"
HTTP_PATH="${TELEGRAM_MCP_HTTP_PATH:-/mcp}"
MOUNT_PATH="${TELEGRAM_MCP_MOUNT_PATH:-/}"
READY_ATTEMPTS="${TELEGRAM_MCP_READY_ATTEMPTS:-15}"
READY_INTERVAL="${TELEGRAM_MCP_READY_INTERVAL:-1}"

: "${TELEGRAM_API_ID:?'TELEGRAM_API_ID must be set in .env or environment'}"
: "${TELEGRAM_API_HASH:?'TELEGRAM_API_HASH must be set in .env or environment'}"
if [ "${TRANSPORT}" != "stdio" ]; then
  : "${TELEGRAM_MCP_AUTH_TOKEN:?'TELEGRAM_MCP_AUTH_TOKEN must be set for launchd HTTP/SSE transports'}"
fi

ensure_python_runtime() {
  if [ -x "${PYTHON_BIN}" ]; then
    return 0
  fi
  printf 'Missing repo-local python at %s.\n' "${PYTHON_BIN}" >&2
  printf 'Bootstrap the local virtualenv with: uv pip install -e .\n' >&2
  exit 1
}

ensure_python_runtime

mkdir -p "${LOG_DIR}" "$(dirname "${PLIST_PATH}")"

bootout_launch_agent() {
  local label="$1"
  local plist_path="$2"
  local domain="gui/$(id -u)"

  launchctl bootout "${domain}" "${plist_path}" 2>/dev/null || \
    launchctl bootout "${domain}/${label}" 2>/dev/null || true
}

run_local_health_probe() {
  TELEGRAM_MCP_TRANSPORT="${TRANSPORT}" \
  TELEGRAM_MCP_HOST="${HOST}" \
  TELEGRAM_MCP_PORT="${PORT}" \
  TELEGRAM_MCP_HTTP_PATH="${HTTP_PATH}" \
  PYTHONPATH="${PYTHONPATH_VALUE}" \
  "${PYTHON_BIN}" - health <<'PY' >/dev/null
from telegram_mcp.auth import run_health

run_health()
PY
}

wait_for_daemon_ready() {
  local attempt=1

  if [ "${TRANSPORT}" = "stdio" ]; then
    return 0
  fi

  printf 'Waiting for daemon readiness via health probe...\n'

  while [ "${attempt}" -le "${READY_ATTEMPTS}" ]; do
    if run_local_health_probe; then
      printf 'Daemon health probe ready on attempt %s.\n' "${attempt}"
      return 0
    fi

    if [ "${attempt}" -lt "${READY_ATTEMPTS}" ]; then
      sleep "${READY_INTERVAL}"
    fi
    attempt=$((attempt + 1))
  done

  printf 'Daemon did not become ready after %s attempts.\n' "${READY_ATTEMPTS}" >&2
  printf 'Try ./scripts/status.sh for details.\n' >&2
  exit 1
}

cat > "${PLIST_PATH}" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${LABEL}</string>

  <key>ProgramArguments</key>
  <array>
    <string>${LAUNCHD_RUNNER}</string>
  </array>

  <key>EnvironmentVariables</key>
  <dict>
    <key>HOME</key>
    <string>${HOME}</string>
    <key>PATH</key>
    <string>${PROJECT_ROOT}/.venv/bin:/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin</string>
    <key>PYTHONPATH</key>
    <string>${PROJECT_ROOT}/src</string>
    <key>TELEGRAM_MCP_TRANSPORT</key>
    <string>${TRANSPORT}</string>
    <key>TELEGRAM_MCP_HOST</key>
    <string>${HOST}</string>
    <key>TELEGRAM_MCP_PORT</key>
    <string>${PORT}</string>
    <key>TELEGRAM_MCP_HTTP_PATH</key>
    <string>${HTTP_PATH}</string>
    <key>TELEGRAM_MCP_MOUNT_PATH</key>
    <string>${MOUNT_PATH}</string>
    <key>TELEGRAM_MCP_ENV_FILE</key>
    <string>${ENV_FILE}</string>
EOF

if [ -n "${TELEGRAM_SESSION_DIR:-}" ]; then
append_xml_string TELEGRAM_SESSION_DIR "${TELEGRAM_SESSION_DIR}"
fi

append_optional_env_var() {
  local key="$1"
  local value="${!key:-}"

  if [ -z "${value}" ]; then
    return 0
  fi

  append_xml_string "${key}" "${value}"
}

append_optional_env_var TELEGRAM_DOWNLOAD_DIR
append_optional_env_var TELEGRAM_DOWNLOAD_REGISTRY_PATH
append_optional_env_var TELEGRAM_DOWNLOAD_RETENTION_DAYS
append_optional_env_var TELEGRAM_DOWNLOAD_CLEANUP_INTERVAL_SECONDS
append_optional_env_var TELEGRAM_MCP_INCLUDE_DIAGNOSTICS
append_optional_env_var TELEGRAM_MCP_JSON_RESPONSE
append_optional_env_var TELEGRAM_MCP_PROBE_TIMEOUT_SECONDS
append_optional_env_var TELEGRAM_CACHE_TTL
append_optional_env_var TELEGRAM_RESULT_CACHE_SIZE
append_optional_env_var TELEGRAM_READ_INFLIGHT_DEDUPE_SIZE
append_optional_env_var TELEGRAM_TRANSCRIPT_CACHE_SIZE
append_optional_env_var TELEGRAM_CONNECT_TIMEOUT_SECONDS
append_optional_env_var TELEGRAM_TOOL_READ_TIMEOUT_SECONDS
append_optional_env_var TELEGRAM_TOOL_WRITE_TIMEOUT_SECONDS
append_optional_env_var TELEGRAM_TOOL_MEDIA_TIMEOUT_SECONDS
append_optional_env_var TELEGRAM_TOOL_TRANSCRIBE_TIMEOUT_SECONDS
append_optional_env_var TELEGRAM_TOOL_ENRICH_TIMEOUT_SECONDS
append_optional_env_var TELEGRAM_SCHEDULER_READ_CONCURRENCY
append_optional_env_var TELEGRAM_SCHEDULER_WRITE_CONCURRENCY
append_optional_env_var TELEGRAM_SCHEDULER_MEDIA_CONCURRENCY
append_optional_env_var TELEGRAM_SCHEDULER_TRANSCRIBE_CONCURRENCY
append_optional_env_var TELEGRAM_SCHEDULER_ENRICH_CONCURRENCY
append_optional_env_var TELEGRAM_CIRCUIT_BREAKER_ENABLED
append_optional_env_var TELEGRAM_CIRCUIT_BREAKER_FAILURE_THRESHOLD
append_optional_env_var TELEGRAM_CIRCUIT_BREAKER_RECOVERY_SECONDS
append_optional_env_var TELEGRAM_DEFAULT_VOICE_TRANSCRIPTION_BUDGET
append_optional_env_var TELEGRAM_READ_MAX_MESSAGES
append_optional_env_var TELEGRAM_READ_MAX_CHARS
append_optional_env_var TELEGRAM_READ_MAX_MEDIA_ITEMS
append_optional_env_var TELEGRAM_WRITE_AUDIT_ENABLED
append_optional_env_var TELEGRAM_WRITE_AUDIT_LOG_PATH

cat >> "${PLIST_PATH}" <<EOF
  </dict>

  <key>WorkingDirectory</key>
  <string>${PROJECT_ROOT}</string>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>ThrottleInterval</key>
  <integer>30</integer>

  <key>StandardOutPath</key>
  <string>${LOG_PATH}</string>
  <key>StandardErrorPath</key>
  <string>${LOG_PATH}</string>
</dict>
</plist>
EOF

bootout_launch_agent "${LABEL}" "${PLIST_PATH}"
launchctl bootstrap "gui/$(id -u)" "${PLIST_PATH}"
wait_for_daemon_ready

printf 'Installed and restarted %s (profile=%s)\n' "${PLIST_PATH}" "${PROFILE}"

# ── Log rotation (daily at 03:00) ──

cat > "${ROTATE_PLIST}" <<ROTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${LOGROTATE_LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>${PROJECT_ROOT}/scripts/rotate-logs.sh</string>
  </array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>TELEGRAM_MCP_LOG</key>
    <string>${LOG_PATH}</string>
  </dict>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key>
    <integer>3</integer>
    <key>Minute</key>
    <integer>0</integer>
  </dict>
</dict>
</plist>
ROTEOF

bootout_launch_agent "${LOGROTATE_LABEL}" "${ROTATE_PLIST}"
launchctl bootstrap "gui/$(id -u)" "${ROTATE_PLIST}"

printf 'Installed log rotation %s\n' "${ROTATE_PLIST}"
