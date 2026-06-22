#!/usr/bin/env bash
# shellcheck disable=SC2034
# Local single-owner Telegram topology. Keep this file shell-only: it is sourced
# by hot-path wrappers such as `tg`, so spawning Python here directly adds
# latency to every agent Telegram read.
set -euo pipefail

_TELEGRAM_ENV_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
_TELEGRAM_HOME="${HOME:?HOME must be set}"

export TELEGRAM_CONTROL_ROOT="${_TELEGRAM_ENV_ROOT}"
export TELEGRAM_MCP_REPO="${_TELEGRAM_HOME}/Projects/families/telegram/telegram-digest/telegram-mcp"
export TELEGRAM_PLUGIN_PACKAGE="${_TELEGRAM_ENV_ROOT}/generated/telegram-plugin-package"
export TELEGRAM_PLUGIN_SOURCE="${_TELEGRAM_HOME}/plugins/telegram"
export TELEGRAM_PLUGIN_CACHE_ROOT="${_TELEGRAM_HOME}/.codex/plugins/cache/sereja-local/telegram"
export TELEGRAM_LIVE_SKILL="${_TELEGRAM_HOME}/.agents/skills/telegram"
export TELEGRAM_LOCAL_MIRROR_SKILL="${_TELEGRAM_HOME}/Projects/.codex/skills/telegram-local-mirror"
export TELEGRAM_MIRROR_ROOT="${_TELEGRAM_HOME}/Projects/tools/telegram-mirror"
export TELEGRAM_MIRROR_RUNTIME_ROOT="${_TELEGRAM_HOME}/Projects/runtime/telegram-mirror"
export TELEGRAM_MIRROR_LEGACY_ALIAS="${_TELEGRAM_HOME}/Projects/tools/hermes-agent-local/workspace/integrations/telegram-mirror"
export TELEGRAM_TELECRAWL_ARCHIVE="${_TELEGRAM_HOME}/Projects/tools/agent-tooling/bin/telecrawl-archive"
export TELEGRAM_TELECRAWL_DEFAULT_DB="${_TELEGRAM_HOME}/Projects/.artifacts/telecrawl/telecrawl-fast.db"
export TELEGRAM_GENERATED_DIR="${_TELEGRAM_ENV_ROOT}/generated"
export TELEGRAM_POLICY_DIR="${_TELEGRAM_ENV_ROOT}/policy"
export TELEGRAM_FAST_READ_ADAPTER="${_TELEGRAM_ENV_ROOT}/bin/telegram-fast-read-today"
export TELEGRAM_TG_CLI="${TELEGRAM_MCP_REPO}/bin/tg"
export TELEGRAM_OBSERVED_REGISTRY="${_TELEGRAM_ENV_ROOT}/generated/observed-registry.json"
export TELEGRAM_LAUNCHAGENTS_DIR="${_TELEGRAM_HOME}/Library/LaunchAgents"
export TELEGRAM_MCP_TELEMETRY_LOG="${_TELEGRAM_HOME}/telegram-mcp/telemetry.jsonl"
export TELEGRAM_MCP_TELEMETRY_DIR="${_TELEGRAM_HOME}/telegram-mcp/telemetry"
export TELEGRAM_MCP_TELEMETRY_STATS="${_TELEGRAM_HOME}/telegram-mcp/telemetry-stats.json"
export TELEGRAM_TELEMETRY_ALERT_THRESHOLDS="${_TELEGRAM_ENV_ROOT}/policy/telemetry/alert-thresholds.json"
