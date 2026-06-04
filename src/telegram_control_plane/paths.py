from __future__ import annotations

import json
from pathlib import Path

from .managed_systems import resolve_topology

_TOPOLOGY = resolve_topology()

HOME = Path.home()
CONTROL_ROOT = _TOPOLOGY["control_root"]
MCP_REPO = _TOPOLOGY["mcp_repo"]
PLUGIN_SOURCE = _TOPOLOGY["plugin_source"]
PLUGIN_CACHE_ROOT = _TOPOLOGY["plugin_cache_root"]
LIVE_SKILL = _TOPOLOGY["live_skill"]
MIRROR_ROOT = _TOPOLOGY["mirror_root"]
MIRROR_RUNTIME_ROOT = _TOPOLOGY["mirror_runtime_root"]
MIRROR_LEGACY_ALIAS = _TOPOLOGY["mirror_legacy_alias"]
TELECRAWL_ARCHIVE = _TOPOLOGY["telecrawl_archive"]
TELECRAWL_DEFAULT_DB = _TOPOLOGY["telecrawl_default_db"]
FAST_READ_ADAPTER = _TOPOLOGY["fast_read_adapter"]
TG_CLI = _TOPOLOGY["tg_cli"]
LAUNCHAGENTS_DIR = _TOPOLOGY["launchagents_dir"]
GENERATED_DIR = _TOPOLOGY["generated_dir"]
PLUGIN_PACKAGE = _TOPOLOGY["plugin_package"]
OBSERVED_REGISTRY = _TOPOLOGY["observed_registry"]
POLICY_DIR = _TOPOLOGY["policy_dir"]
MCP_TELEMETRY_LOG = _TOPOLOGY["mcp_telemetry_log"]
MCP_TELEMETRY_DIR = _TOPOLOGY["mcp_telemetry_dir"]
MCP_TELEMETRY_STATS = _TOPOLOGY["mcp_telemetry_stats"]
TELEMETRY_ALERT_THRESHOLDS = _TOPOLOGY["telemetry_alert_thresholds"]


def plugin_source_version() -> str | None:
    manifest = PLUGIN_SOURCE / ".codex-plugin/plugin.json"
    try:
        data = json.loads(manifest.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    version = data.get("version")
    return version if isinstance(version, str) and version else None


def _plugin_source_version() -> str | None:
    return plugin_source_version()


def _latest_plugin_cache() -> Path:
    source_version = _plugin_source_version()
    if source_version:
        candidate = PLUGIN_CACHE_ROOT / source_version
        if candidate.exists():
            return candidate
    versions = sorted(path for path in PLUGIN_CACHE_ROOT.glob("*") if path.is_dir())
    return versions[-1] if versions else PLUGIN_CACHE_ROOT


PLUGIN_CACHE = _latest_plugin_cache()