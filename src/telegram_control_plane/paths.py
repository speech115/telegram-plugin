from __future__ import annotations

import json
from pathlib import Path


HOME = Path("/Users/sereja")
CONTROL_ROOT = Path("/Users/sereja/Projects/tools/telegram")
MCP_REPO = Path("/Users/sereja/Projects/families/telegram/telegram-digest/telegram-mcp")
PLUGIN_SOURCE = Path("/Users/sereja/plugins/telegram")
PLUGIN_CACHE_ROOT = Path("/Users/sereja/.codex/plugins/cache/sereja-local/telegram")
LIVE_SKILL = Path("/Users/sereja/.agents/skills/telegram")
MIRROR_ROOT = Path("/Users/sereja/Projects/tools/telegram-mirror")
MIRROR_LEGACY_ALIAS = Path("/Users/sereja/Projects/tools/hermes-agent-local/workspace/integrations/telegram-mirror")
TELECRAWL_ARCHIVE = Path("/Users/sereja/Projects/tools/agent-tooling/bin/telecrawl-archive")
TELECRAWL_DEFAULT_DB = Path("/Users/sereja/Projects/.artifacts/telecrawl/telecrawl-fast.db")
FAST_READ_ADAPTER = CONTROL_ROOT / "bin/telegram-fast-read-today"
LAUNCHAGENTS_DIR = HOME / "Library/LaunchAgents"
GENERATED_DIR = CONTROL_ROOT / "generated"
OBSERVED_REGISTRY = GENERATED_DIR / "observed-registry.json"
POLICY_DIR = CONTROL_ROOT / "policy"


def _plugin_source_version() -> str | None:
    manifest = PLUGIN_SOURCE / ".codex-plugin/plugin.json"
    try:
        data = json.loads(manifest.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    version = data.get("version")
    return version if isinstance(version, str) and version else None


def _latest_plugin_cache() -> Path:
    source_version = _plugin_source_version()
    if source_version:
        candidate = PLUGIN_CACHE_ROOT / source_version
        if candidate.exists():
            return candidate
    versions = sorted(path for path in PLUGIN_CACHE_ROOT.glob("*") if path.is_dir())
    return versions[-1] if versions else PLUGIN_CACHE_ROOT


PLUGIN_CACHE = _latest_plugin_cache()
