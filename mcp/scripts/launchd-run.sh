#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
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

load_env_file() {
  local line key value

  [ -f "${ENV_FILE}" ] || return 0
  if [ ! -O "${ENV_FILE}" ]; then
    printf 'Refusing env file not owned by current user: %s\n' "${ENV_FILE}" >&2
    exit 1
  fi
  if [ "$(stat -f '%OLp' "${ENV_FILE}")" != "600" ] && [ "$(stat -f '%OLp' "${ENV_FILE}")" != "400" ]; then
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
    reject_unsafe_env_value "${key}" "${value}"
    export "${key}=${value}"
  done < "${ENV_FILE}"
}

if [ -f "${ENV_FILE}" ]; then
  load_env_file
fi

exec "${PROJECT_ROOT}/.venv/bin/python" -m telegram_mcp
