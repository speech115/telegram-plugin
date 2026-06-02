from __future__ import annotations

import json
import os
from pathlib import Path


def _path_from_env(name: str, default: str | Path) -> Path:
    return Path(os.environ.get(name, str(default))).expanduser()


HOME = Path.home()
PROJECTS_ROOT = _path_from_env("TELEGRAM_PROJECTS_ROOT", HOME / "Projects")
CONTROL_ROOT = _path_from_env("TELEGRAM_CONTROL_PLANE_ROOT", Path(__file__).resolve().parents[2])
MONOREPO_ROOT = CONTROL_ROOT.parent
MCP_REPO = _path_from_env("TELEGRAM_MCP_REPO", MONOREPO_ROOT / "mcp")
PLUGIN_SOURCE = _path_from_env("TELEGRAM_PLUGIN_SOURCE", MONOREPO_ROOT / "plugin")
PLUGIN_PACKAGE = _path_from_env("TELEGRAM_PLUGIN_PACKAGE", PLUGIN_SOURCE)
PLUGIN_CACHE_ROOT = _path_from_env("TELEGRAM_PLUGIN_CACHE_ROOT", HOME / ".codex/plugins/cache/local/telegram")
LIVE_SKILL = _path_from_env("TELEGRAM_LIVE_SKILL", HOME / ".agents/skills/telegram")
MIRROR_ROOT = _path_from_env("TELEGRAM_MIRROR_ROOT", PROJECTS_ROOT / "tools" / "telegram-mirror")
MIRROR_RUNTIME_ROOT = _path_from_env(
    "TELEGRAM_MIRROR_RUNTIME_ROOT",
    PROJECTS_ROOT / "runtime" / "telegram-mirror",
)
MIRROR_LEGACY_ALIAS = _path_from_env("TELEGRAM_MIRROR_LEGACY_ALIAS", MIRROR_ROOT)
TELECRAWL_ARCHIVE = Path(os.environ.get("TELECRAWL_ARCHIVE_BIN", "telecrawl-archive"))
TELECRAWL_ARTIFACT_ROOT = _path_from_env("TELECRAWL_ARTIFACT_ROOT", PROJECTS_ROOT / ".artifacts" / "telecrawl")
TELECRAWL_DEFAULT_DB = _path_from_env("TELECRAWL_DEFAULT_DB", TELECRAWL_ARTIFACT_ROOT / "telecrawl-fast.db")
LAUNCHAGENTS_DIR = HOME / "Library" / "LaunchAgents"
GENERATED_DIR = CONTROL_ROOT / "generated"
OBSERVED_REGISTRY = GENERATED_DIR / "observed-registry.json"
POLICY_DIR = CONTROL_ROOT / "policy"
FAST_READ_ADAPTER = CONTROL_ROOT / "bin" / "telegram-fast-read-today"


def plugin_source_version() -> str | None:
    manifest = PLUGIN_SOURCE / ".codex-plugin/plugin.json"
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
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