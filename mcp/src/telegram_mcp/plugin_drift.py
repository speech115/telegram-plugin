"""Read-only diagnostics for local Telegram plugin source drift."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path


DEFAULT_LIVE_SKILL_PATH = Path("~/.agents/skills/telegram/SKILL.md")
DEFAULT_PLUGIN_SOURCE_SKILL_PATH = Path("~/plugins/telegram/skills/telegram/SKILL.md")
AUTO_PATH = "auto"
DEFAULT_PLUGIN_CACHE_ROOT = Path("~/.codex/plugins/cache/sereja-local/telegram")
DEFAULT_PLUGIN_SOURCE_MCP_PATH = Path("~/plugins/telegram/.mcp.json")
DEFAULT_CODEX_CONFIG_PATH = Path("~/.codex/config.toml")
DEFAULT_LOCAL_MARKETPLACE_PATH = Path("~/.agents/plugins/marketplace.json")


@dataclass(frozen=True)
class SkillFileState:
    path: str
    exists: bool
    size_bytes: int | None
    sha256: str | None


@dataclass(frozen=True)
class JsonFileState:
    path: str
    exists: bool
    valid_json: bool
    sha256: str | None
    error: str | None


@dataclass(frozen=True)
class PluginManifestState:
    path: str
    exists: bool
    valid_json: bool
    name: str | None
    version: str | None
    sha256: str | None
    error: str | None


@dataclass(frozen=True)
class CodexPluginConfigState:
    path: str
    exists: bool
    valid_toml: bool
    plugin_key: str
    enabled: bool
    marketplace_name: str
    marketplace_source: str | None
    error: str | None


@dataclass(frozen=True)
class MarketplaceState:
    path: str
    exists: bool
    valid_json: bool
    name: str | None
    plugin_declared: bool
    declared_source_path: str | None
    resolved_source_path: str | None
    error: str | None


@dataclass(frozen=True)
class InstallerFlowState:
    command: list[str]
    marketplace_name: str
    source_path: str | None
    safe_to_apply: bool
    reason: str


@dataclass(frozen=True)
class TreeState:
    path: str | None
    exists: bool
    file_count: int
    sha256: str | None


@dataclass(frozen=True)
class DriftReport:
    status: str
    live_skill: SkillFileState
    plugin_source_skill: SkillFileState
    marketplace_skill: SkillFileState
    plugin_cache_skill: SkillFileState
    plugin_source_manifest: PluginManifestState
    plugin_cache_manifest: PluginManifestState
    plugin_source_mcp: JsonFileState
    plugin_cache_mcp: JsonFileState
    codex_plugin_config: CodexPluginConfigState
    local_marketplace: MarketplaceState
    installer_flow: InstallerFlowState
    canonical_source: str
    sync_safe: bool
    source_candidates: list[str]
    recommendation: str
    live_skill_tree: TreeState
    plugin_source_skill_tree: TreeState
    marketplace_skill_tree: TreeState
    plugin_cache_skill_tree: TreeState
    plugin_source_package_tree: TreeState
    plugin_cache_package_tree: TreeState
    tree_diff: dict[str, dict[str, list[str]]]


def _expand_path(raw_path: str | Path) -> Path:
    return Path(raw_path).expanduser().resolve()


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _hash_tree(root: Path | None, *, ignored_root_files: set[str] | None = None) -> tuple[TreeState, dict[str, str]]:
    if root is None or not root.exists() or not root.is_dir():
        return TreeState(path=str(root) if root is not None else None, exists=False, file_count=0, sha256=None), {}

    resolved_root = root.resolve()
    ignored_root_files = ignored_root_files or set()
    files: dict[str, str] = {}
    for path in sorted(resolved_root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(resolved_root).as_posix()
        if "/" not in relative and relative in ignored_root_files:
            continue
        files[relative] = _hash_file(path)

    digest = hashlib.sha256()
    for relative, sha256 in files.items():
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(sha256.encode("ascii"))
        digest.update(b"\0")
    return TreeState(path=str(root), exists=True, file_count=len(files), sha256=digest.hexdigest()), files


def _tree_diff(left: dict[str, str], right: dict[str, str]) -> dict[str, list[str]]:
    left_keys = set(left)
    right_keys = set(right)
    common = left_keys & right_keys
    return {
        "left_only": sorted(left_keys - right_keys)[:20],
        "right_only": sorted(right_keys - left_keys)[:20],
        "changed": sorted(key for key in common if left.get(key) != right.get(key))[:20],
    }


def _read_state(path: Path) -> SkillFileState:
    if not path.exists():
        return SkillFileState(
            path=str(path),
            exists=False,
            size_bytes=None,
            sha256=None,
        )
    stat = path.stat()
    return SkillFileState(
        path=str(path),
        exists=True,
        size_bytes=stat.st_size,
        sha256=_hash_file(path),
    )


def _read_json_state(path: Path) -> JsonFileState:
    if not path.exists():
        return JsonFileState(
            path=str(path),
            exists=False,
            valid_json=False,
            sha256=None,
            error="missing",
        )

    sha256 = _hash_file(path)
    try:
        with path.open("r", encoding="utf-8") as handle:
            json.load(handle)
    except json.JSONDecodeError as exc:
        return JsonFileState(
            path=str(path),
            exists=True,
            valid_json=False,
            sha256=sha256,
            error=f"invalid_json: {exc.msg}",
        )

    return JsonFileState(
        path=str(path),
        exists=True,
        valid_json=True,
        sha256=sha256,
        error=None,
    )


def _read_plugin_manifest(path: Path) -> PluginManifestState:
    if not path.exists():
        return PluginManifestState(
            path=str(path),
            exists=False,
            valid_json=False,
            name=None,
            version=None,
            sha256=None,
            error="missing",
        )

    sha256 = _hash_file(path)
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except json.JSONDecodeError as exc:
        return PluginManifestState(
            path=str(path),
            exists=True,
            valid_json=False,
            name=None,
            version=None,
            sha256=sha256,
            error=f"invalid_json: {exc.msg}",
        )

    return PluginManifestState(
        path=str(path),
        exists=True,
        valid_json=True,
        name=payload.get("name") if isinstance(payload.get("name"), str) else None,
        version=payload.get("version") if isinstance(payload.get("version"), str) else None,
        sha256=sha256,
        error=None,
    )


def _marketplace_name_from_plugin_key(plugin_key: str) -> str:
    if "@" not in plugin_key:
        return "sereja-local"
    return plugin_key.rsplit("@", 1)[1]


def _read_codex_plugin_config(path: Path, plugin_key: str = "telegram@sereja-local") -> CodexPluginConfigState:
    marketplace_name = _marketplace_name_from_plugin_key(plugin_key)
    if not path.exists():
        return CodexPluginConfigState(
            path=str(path),
            exists=False,
            valid_toml=False,
            plugin_key=plugin_key,
            enabled=False,
            marketplace_name=marketplace_name,
            marketplace_source=None,
            error="missing",
        )

    try:
        with path.open("rb") as handle:
            payload = tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        return CodexPluginConfigState(
            path=str(path),
            exists=True,
            valid_toml=False,
            plugin_key=plugin_key,
            enabled=False,
            marketplace_name=marketplace_name,
            marketplace_source=None,
            error=f"invalid_toml: {exc}",
        )

    plugins_payload = payload.get("plugins", {})
    if plugin_key not in plugins_payload:
        telegram_keys = sorted(
            key for key in plugins_payload if isinstance(key, str) and key.startswith("telegram@")
        )
        if telegram_keys:
            plugin_key = telegram_keys[0]
            marketplace_name = _marketplace_name_from_plugin_key(plugin_key)
    plugin_payload = plugins_payload.get(plugin_key, {})
    marketplace_payload = payload.get("marketplaces", {}).get(marketplace_name, {})
    return CodexPluginConfigState(
        path=str(path),
        exists=True,
        valid_toml=True,
        plugin_key=plugin_key,
        enabled=bool(plugin_payload.get("enabled", False)),
        marketplace_name=marketplace_name,
        marketplace_source=marketplace_payload.get("source")
        if isinstance(marketplace_payload.get("source"), str)
        else None,
        error=None,
    )


def _resolve_local_plugin_source(marketplace_path: Path, raw_path: str) -> Path:
    if raw_path.startswith("./plugins/"):
        marketplace_file = marketplace_path.expanduser()
        if marketplace_file.parent.name == "plugins" and marketplace_file.parent.parent.name == ".agents":
            return marketplace_file.parent.parent.parent / raw_path.removeprefix("./")
        return marketplace_file.parent / raw_path.removeprefix("./")
    return (marketplace_path.parent / raw_path).expanduser().resolve()


def _read_marketplace(path: Path, plugin_name: str = "telegram") -> MarketplaceState:
    if not path.exists():
        return MarketplaceState(
            path=str(path),
            exists=False,
            valid_json=False,
            name=None,
            plugin_declared=False,
            declared_source_path=None,
            resolved_source_path=None,
            error="missing",
        )

    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except json.JSONDecodeError as exc:
        return MarketplaceState(
            path=str(path),
            exists=True,
            valid_json=False,
            name=None,
            plugin_declared=False,
            declared_source_path=None,
            resolved_source_path=None,
            error=f"invalid_json: {exc.msg}",
        )

    plugin_entries = payload.get("plugins", [])
    plugin_entry = next((entry for entry in plugin_entries if entry.get("name") == plugin_name), None)
    declared_source_path = None
    resolved_source_path = None
    if plugin_entry:
        declared_source_path = plugin_entry.get("source", {}).get("path")
        if declared_source_path:
            resolved_source_path = str(_resolve_local_plugin_source(path, declared_source_path))

    return MarketplaceState(
        path=str(path),
        exists=True,
        valid_json=True,
        name=payload.get("name"),
        plugin_declared=plugin_entry is not None,
        declared_source_path=declared_source_path,
        resolved_source_path=resolved_source_path,
        error=None,
    )


def _existing_skill_candidates(states: dict[str, SkillFileState]) -> list[str]:
    return [name for name, state in states.items() if state.exists]


def _all_same_hash(states: list[SkillFileState]) -> bool:
    existing = [state for state in states if state.exists]
    hashes = {state.sha256 for state in existing}
    return len(existing) >= 2 and len(hashes) == 1


def _same_hash(left: SkillFileState, right: SkillFileState) -> bool:
    return left.exists and right.exists and left.sha256 == right.sha256


def _same_tree(left: TreeState, right: TreeState) -> bool:
    return left.exists and right.exists and left.sha256 == right.sha256


def _same_skill_layer(
    left_file: SkillFileState,
    right_file: SkillFileState,
    left_tree: TreeState,
    right_tree: TreeState,
) -> bool:
    return _same_hash(left_file, right_file) and _same_tree(left_tree, right_tree)


def _all_same_skill_layers(states: list[tuple[SkillFileState, TreeState]]) -> bool:
    existing = [(file_state, tree_state) for file_state, tree_state in states if file_state.exists]
    file_hashes = {file_state.sha256 for file_state, _ in existing}
    tree_hashes = {tree_state.sha256 for _, tree_state in existing if tree_state.exists}
    return len(existing) >= 2 and len(file_hashes) == 1 and len(tree_hashes) == 1


def _skill_dir_from_skill_file(path: Path) -> Path:
    return path.parent


def _plugin_root_from_skill_file(path: Path) -> Path | None:
    if path.name != "SKILL.md" or len(path.parents) < 3:
        return None
    if path.parent.name != "telegram" or path.parent.parent.name != "skills":
        return None
    root = path.parents[2]
    return root if _looks_like_plugin_root(root) else None


def _looks_like_plugin_root(path: Path) -> bool:
    return (
        (path / ".codex-plugin" / "plugin.json").is_file()
        or (path / ".mcp.json").is_file()
        or (path / "skills" / "telegram" / "SKILL.md").is_file()
    )


def _resolve_marketplace_root(
    codex_config: CodexPluginConfigState,
    local_marketplace_path: Path,
) -> Path:
    if codex_config.marketplace_source:
        return _expand_path(codex_config.marketplace_source)
    return _expand_path(local_marketplace_path).parents[2]


def _resolve_marketplace_skill_path(
    *,
    codex_config: CodexPluginConfigState,
    local_marketplace: MarketplaceState,
    local_marketplace_path: Path,
) -> Path:
    marketplace_root = _resolve_marketplace_root(codex_config, local_marketplace_path)
    declared_path = local_marketplace.declared_source_path or "./plugins/telegram"
    plugin_root = _resolve_local_plugin_source(marketplace_root / ".agents" / "plugins" / "marketplace.json", declared_path)
    return plugin_root / "skills" / "telegram" / "SKILL.md"


def _resolve_cache_plugin_root(
    *,
    plugin_cache_root: str | Path,
    source_manifest: PluginManifestState,
) -> Path:
    root = _expand_path(plugin_cache_root)
    if source_manifest.version:
        return root / source_manifest.version
    return root / "0.1.0"


def _installer_command(
    *,
    marketplace_name: str,
    codex_config: CodexPluginConfigState,
) -> list[str]:
    plugin_key = f"telegram@{marketplace_name}" if marketplace_name else "telegram"
    return ["codex", "plugin", "remove", plugin_key, "&&", "codex", "plugin", "add", plugin_key]


def check_plugin_drift(
    *,
    live_skill_path: str | Path = DEFAULT_LIVE_SKILL_PATH,
    plugin_source_skill_path: str | Path = DEFAULT_PLUGIN_SOURCE_SKILL_PATH,
    marketplace_skill_path: str | Path = AUTO_PATH,
    plugin_cache_skill_path: str | Path = AUTO_PATH,
    plugin_cache_root: str | Path = DEFAULT_PLUGIN_CACHE_ROOT,
    plugin_source_mcp_path: str | Path = DEFAULT_PLUGIN_SOURCE_MCP_PATH,
    plugin_cache_mcp_path: str | Path = AUTO_PATH,
    codex_config_path: str | Path = DEFAULT_CODEX_CONFIG_PATH,
    local_marketplace_path: str | Path = DEFAULT_LOCAL_MARKETPLACE_PATH,
) -> DriftReport:
    live = _read_state(_expand_path(live_skill_path))
    source = _read_state(_expand_path(plugin_source_skill_path))
    plugin_source_manifest_path = _expand_path(plugin_source_skill_path).parents[2] / ".codex-plugin" / "plugin.json"
    source_manifest = _read_plugin_manifest(plugin_source_manifest_path)
    codex_config = _read_codex_plugin_config(_expand_path(codex_config_path))
    local_marketplace_path_expanded = _expand_path(local_marketplace_path)
    local_marketplace = _read_marketplace(local_marketplace_path_expanded)
    if os.fspath(marketplace_skill_path) == AUTO_PATH:
        resolved_marketplace_skill_path = _resolve_marketplace_skill_path(
            codex_config=codex_config,
            local_marketplace=local_marketplace,
            local_marketplace_path=local_marketplace_path_expanded,
        )
    else:
        resolved_marketplace_skill_path = _expand_path(marketplace_skill_path)
    cache_plugin_root = _resolve_cache_plugin_root(
        plugin_cache_root=plugin_cache_root,
        source_manifest=source_manifest,
    )
    if os.fspath(plugin_cache_skill_path) == AUTO_PATH:
        resolved_cache_skill_path = cache_plugin_root / "skills" / "telegram" / "SKILL.md"
    else:
        resolved_cache_skill_path = _expand_path(plugin_cache_skill_path)
        cache_plugin_root = resolved_cache_skill_path.parents[2]
    if os.fspath(plugin_cache_mcp_path) == AUTO_PATH:
        resolved_cache_mcp_path = cache_plugin_root / ".mcp.json"
    else:
        resolved_cache_mcp_path = _expand_path(plugin_cache_mcp_path)
    staged = _read_state(resolved_marketplace_skill_path)
    cache = _read_state(resolved_cache_skill_path)
    cache_manifest = _read_plugin_manifest(cache_plugin_root / ".codex-plugin" / "plugin.json")
    source_mcp = _read_json_state(_expand_path(plugin_source_mcp_path))
    cache_mcp = _read_json_state(resolved_cache_mcp_path)
    skill_tree_ignored_root_files = {".mcp.json"}
    live_tree, live_tree_files = _hash_tree(
        _skill_dir_from_skill_file(_expand_path(live_skill_path)),
        ignored_root_files=skill_tree_ignored_root_files,
    )
    source_tree, source_tree_files = _hash_tree(
        _skill_dir_from_skill_file(_expand_path(plugin_source_skill_path)),
        ignored_root_files=skill_tree_ignored_root_files,
    )
    staged_tree, staged_tree_files = _hash_tree(
        _skill_dir_from_skill_file(resolved_marketplace_skill_path),
        ignored_root_files=skill_tree_ignored_root_files,
    )
    cache_tree, cache_tree_files = _hash_tree(
        _skill_dir_from_skill_file(resolved_cache_skill_path),
        ignored_root_files=skill_tree_ignored_root_files,
    )
    source_package_tree, source_package_files = _hash_tree(_plugin_root_from_skill_file(_expand_path(plugin_source_skill_path)))
    cache_package_tree, cache_package_files = _hash_tree(cache_plugin_root if _looks_like_plugin_root(cache_plugin_root) else None)
    tree_diff: dict[str, dict[str, list[str]]] = {}
    if source_tree.exists and live_tree.exists and source_tree.sha256 != live_tree.sha256:
        tree_diff["plugin_source_vs_live_skill_tree"] = _tree_diff(source_tree_files, live_tree_files)
    if source_tree.exists and staged_tree.exists and source_tree.sha256 != staged_tree.sha256:
        tree_diff["plugin_source_vs_marketplace_skill_tree"] = _tree_diff(source_tree_files, staged_tree_files)
    if source_tree.exists and cache_tree.exists and source_tree.sha256 != cache_tree.sha256:
        tree_diff["plugin_source_vs_cache_skill_tree"] = _tree_diff(source_tree_files, cache_tree_files)
    if source_package_tree.exists and cache_package_tree.exists and source_package_tree.sha256 != cache_package_tree.sha256:
        tree_diff["plugin_source_vs_cache_package_tree"] = _tree_diff(source_package_files, cache_package_files)
    skill_states = {
        "live_skill": live,
        "plugin_source_skill": source,
        "marketplace_skill": staged,
        "plugin_cache_skill": cache,
    }
    mcp_metadata_drift = (
        source_mcp.exists
        and cache_mcp.exists
        and source_mcp.sha256 is not None
        and cache_mcp.sha256 is not None
        and source_mcp.sha256 != cache_mcp.sha256
    )
    source_candidates = _existing_skill_candidates(skill_states)
    installer_marketplace_name = local_marketplace.name or codex_config.marketplace_name
    installer_command = _installer_command(
        marketplace_name=installer_marketplace_name,
        codex_config=codex_config,
    )
    installer_safe = False
    installer_reason = "source-of-truth not proven"

    if not source_candidates:
        status = "missing"
        canonical_source = "unproven"
        sync_safe = False
        recommendation = "No Telegram skill files were found; install the Telegram skill/plugin first."
    elif not live.exists:
        status = "live_missing"
        canonical_source = "unproven"
        sync_safe = False
        recommendation = "Standalone live skill is missing; do not infer agent routing from plugin cache."
    elif not cache.exists and not _same_hash(live, source):
        status = "cache_missing"
        canonical_source = "unproven"
        sync_safe = False
        recommendation = "Plugin cache skill is missing and source does not match live skill; repair source first."
    elif mcp_metadata_drift:
        status = "metadata_drift"
        source_matches_live = _same_skill_layer(live, source, live_tree, source_tree)
        canonical_source = "plugin_source_skill" if source_matches_live else "unproven"
        sync_safe = source_matches_live
        installer_safe = codex_config.enabled and local_marketplace.plugin_declared and source_mcp.valid_json
        installer_reason = (
            "plugin source MCP metadata differs from installed cache and can repair cache through installer flow"
            if installer_safe
            else "plugin source MCP metadata differs from installed cache"
        )
        recommendation = (
            "Plugin source and installed cache MCP metadata differ. Materialize a new versioned "
            "cache from the canonical source before treating the installed plugin as current."
        )
    elif all(state.exists for state in (live, source, staged, cache)) and _all_same_skill_layers(
        [
            (live, live_tree),
            (source, source_tree),
            (staged, staged_tree),
            (cache, cache_tree),
        ]
    ) and (
        not source_package_tree.exists
        or not cache_package_tree.exists
        or _same_tree(source_package_tree, cache_package_tree)
    ):
        status = "ok"
        canonical_source = "plugin_source_skill"
        sync_safe = True
        installer_safe = codex_config.enabled and local_marketplace.plugin_declared and source_mcp.valid_json
        installer_reason = (
            "plugin source, live skill, configured marketplace, and cache match"
            if installer_safe
            else "plugin files match, but Codex config/marketplace/MCP metadata is incomplete"
        )
        recommendation = "All known Telegram skill layers match; plugin source can be treated as canonical."
    elif _same_skill_layer(live, source, live_tree, source_tree) and not _same_skill_layer(source, cache, source_tree, cache_tree):
        status = "installer_ready_drift"
        canonical_source = "plugin_source_skill"
        sync_safe = True
        installer_safe = codex_config.enabled and local_marketplace.plugin_declared and source_mcp.valid_json
        installer_reason = (
            "plugin source matches the live skill and can repair installed cache through the installer flow"
            if installer_safe
            else "plugin source matches live skill, but Codex config/marketplace/MCP metadata is incomplete"
        )
        recommendation = (
            "Plugin source matches the live skill while installed layers differ. "
            "Use the Codex installer flow when available; for local marketplaces, materialize only "
            "a new versioned cache from the canonical source and leave older cache versions intact."
        )
    elif _same_skill_layer(staged, cache, staged_tree, cache_tree) and not _same_skill_layer(source, cache, source_tree, cache_tree):
        status = "source_drift"
        canonical_source = "unproven"
        sync_safe = False
        recommendation = (
            "Plugin cache matches the marketplace copy, but the plugin source differs. "
            "Do not apply sync from source until the install flow is proven."
        )
    else:
        status = "drift"
        canonical_source = "unproven"
        sync_safe = False
        recommendation = (
            "Known Telegram skill layers differ. Treat the live skill as current agent "
            "routing, then prove the plugin install/sync flow before applying changes "
            "to managed cache files."
        )

    return DriftReport(
        status=status,
        live_skill=live,
        plugin_source_skill=source,
        marketplace_skill=staged,
        plugin_cache_skill=cache,
        plugin_source_manifest=source_manifest,
        plugin_cache_manifest=cache_manifest,
        plugin_source_mcp=source_mcp,
        plugin_cache_mcp=cache_mcp,
        canonical_source=canonical_source,
        sync_safe=sync_safe,
        source_candidates=source_candidates,
        codex_plugin_config=codex_config,
        local_marketplace=local_marketplace,
        installer_flow=InstallerFlowState(
            command=installer_command,
            marketplace_name=installer_marketplace_name,
            source_path=local_marketplace.resolved_source_path,
            safe_to_apply=installer_safe,
            reason=installer_reason,
        ),
        recommendation=recommendation,
        live_skill_tree=live_tree,
        plugin_source_skill_tree=source_tree,
        marketplace_skill_tree=staged_tree,
        plugin_cache_skill_tree=cache_tree,
        plugin_source_package_tree=source_package_tree,
        plugin_cache_package_tree=cache_package_tree,
        tree_diff=tree_diff,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Check whether the local Telegram live skill differs from plugin cache."
    )
    parser.add_argument(
        "--live-skill",
        default=os.fspath(DEFAULT_LIVE_SKILL_PATH),
        help="Path to the live standalone Telegram SKILL.md.",
    )
    parser.add_argument(
        "--plugin-cache-skill",
        default=AUTO_PATH,
        help="Path to the Telegram plugin cache SKILL.md, or 'auto' for source-version cache.",
    )
    parser.add_argument(
        "--plugin-source-skill",
        default=os.fspath(DEFAULT_PLUGIN_SOURCE_SKILL_PATH),
        help="Path to the source Telegram plugin SKILL.md.",
    )
    parser.add_argument(
        "--marketplace-skill",
        default=AUTO_PATH,
        help="Path to the configured marketplace Telegram SKILL.md, or 'auto'.",
    )
    parser.add_argument(
        "--plugin-cache-root",
        default=os.fspath(DEFAULT_PLUGIN_CACHE_ROOT),
        help="Root path for cached Telegram plugin versions.",
    )
    parser.add_argument(
        "--plugin-source-mcp",
        default=os.fspath(DEFAULT_PLUGIN_SOURCE_MCP_PATH),
        help="Path to the source Telegram plugin .mcp.json.",
    )
    parser.add_argument(
        "--plugin-cache-mcp",
        default=AUTO_PATH,
        help="Path to the cached Telegram plugin .mcp.json, or 'auto'.",
    )
    parser.add_argument(
        "--codex-config",
        default=os.fspath(DEFAULT_CODEX_CONFIG_PATH),
        help="Path to Codex config.toml.",
    )
    parser.add_argument(
        "--local-marketplace",
        default=os.fspath(DEFAULT_LOCAL_MARKETPLACE_PATH),
        help="Path to the local Codex marketplace.json.",
    )
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero when files are missing or differ.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    report = check_plugin_drift(
        live_skill_path=args.live_skill,
        plugin_source_skill_path=args.plugin_source_skill,
        marketplace_skill_path=args.marketplace_skill,
        plugin_cache_skill_path=args.plugin_cache_skill,
        plugin_cache_root=args.plugin_cache_root,
        plugin_source_mcp_path=args.plugin_source_mcp,
        plugin_cache_mcp_path=args.plugin_cache_mcp,
        codex_config_path=args.codex_config,
        local_marketplace_path=args.local_marketplace,
    )

    payload = asdict(report)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"status: {report.status}")
        print(f"canonical source: {report.canonical_source}")
        print(f"sync safe: {str(report.sync_safe).lower()}")
        print(f"live skill: {report.live_skill.path}")
        print(f"plugin source skill: {report.plugin_source_skill.path}")
        print(f"marketplace skill: {report.marketplace_skill.path}")
        print(f"plugin cache skill: {report.plugin_cache_skill.path}")
        if report.live_skill.sha256:
            print(f"live sha256: {report.live_skill.sha256}")
        if report.plugin_source_skill.sha256:
            print(f"source sha256: {report.plugin_source_skill.sha256}")
        if report.marketplace_skill.sha256:
            print(f"marketplace sha256: {report.marketplace_skill.sha256}")
        if report.plugin_cache_skill.sha256:
            print(f"cache sha256: {report.plugin_cache_skill.sha256}")
        if report.plugin_source_skill_tree.sha256:
            print(f"source skill tree sha256: {report.plugin_source_skill_tree.sha256}")
        if report.plugin_cache_skill_tree.sha256:
            print(f"cache skill tree sha256: {report.plugin_cache_skill_tree.sha256}")
        if report.plugin_source_package_tree.sha256:
            print(f"source package tree sha256: {report.plugin_source_package_tree.sha256}")
        if report.plugin_cache_package_tree.sha256:
            print(f"cache package tree sha256: {report.plugin_cache_package_tree.sha256}")
        print(
            "source manifest: "
            f"{report.plugin_source_manifest.path} "
            f"version={report.plugin_source_manifest.version or 'unknown'}"
        )
        print(
            "cache manifest: "
            f"{report.plugin_cache_manifest.path} "
            f"version={report.plugin_cache_manifest.version or 'unknown'}"
        )
        print(f"plugin source mcp: {report.plugin_source_mcp.path}")
        print(f"plugin cache mcp: {report.plugin_cache_mcp.path}")
        print(f"codex plugin enabled: {str(report.codex_plugin_config.enabled).lower()}")
        print(f"marketplace: {report.local_marketplace.path}")
        print(f"installer command: {' '.join(report.installer_flow.command)}")
        print(f"installer safe: {str(report.installer_flow.safe_to_apply).lower()}")
        print(f"recommendation: {report.recommendation}")

    if args.strict and report.status != "ok":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
