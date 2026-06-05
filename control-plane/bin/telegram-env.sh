#!/usr/bin/env bash
# shellcheck disable=SC2034
# Resolve Telegram topology paths from policy/managed-systems.json.
set -euo pipefail

_TELEGRAM_ENV_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if ! eval "$(PYTHONPATH="${_TELEGRAM_ENV_ROOT}/src" python3 -c "from telegram_control_plane.managed_systems import shell_exports; print(shell_exports())")"; then
  printf 'telegram-env: failed to resolve managed-system topology\n' >&2
  return 1 2>/dev/null || exit 1
fi