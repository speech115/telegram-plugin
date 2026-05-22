from __future__ import annotations

import ast
import copy
import json
import plistlib
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .paths import (
    LAUNCHAGENTS_DIR,
    LIVE_SKILL,
    MCP_REPO,
    MIRROR_LEGACY_ALIAS,
    MIRROR_ROOT,
    POLICY_DIR,
    PLUGIN_CACHE,
    PLUGIN_SOURCE,
    TELECRAWL_ARCHIVE,
)
from .util import file_sha256, load_json, run_json, status_from_findings


APPROVED_FACADE_TOOLS = {
    "doctor_check",
    "get_me",
    "resolve_dialog",
    "find_dialog",
    "read_dialog_by_date",
    "read_today_dialog",
    "read_recent_dialog",
    "read_dialog",
    "collect_dialog_context",
    "collect_context",
    "prepare_dialog_reply",
    "draft_reply",
    "prepare_send_message",
    "prepare_reply_message",
    "search_dialog_messages",
}

WRITE_OR_DESTRUCTIVE_RE = re.compile(
    r"^(create|delete|demote|edit|forward|import|invite|leave|mark|promote|reply|send|set|update)_"
)
PATH_LIKE_RE = re.compile(r"^(/Users/sereja/Projects|/Users/sereja/\.|/tmp|/private/tmp|/opt|/usr/local|/bin|/usr/bin)")

SECRET_ENV_KEYS = {"TELEGRAM_API_HASH", "TELEGRAM_SESSION_STRING"}
PRIVATE_KEYS = {
    "db_path",
    "manifest_path",
    "path",
    "phone_masked",
    "telegram_user_id",
    "tdata_path",
    "username",
}
PRIVATE_PATH_SUBSTRINGS = (
    ".session",
    "telegram_user_id",
    "/Users/sereja/.telegram-mcp",
    "/Users/sereja/.telegram-mcp-pl",
    "/Users/sereja/Library/Application Support/Telegram Desktop/tdata",
    "/Users/sereja/Projects/.artifacts/telecrawl",
)


def audit_plugin_drift() -> dict[str, Any]:
    command = [str(MCP_REPO / "bin/check-plugin-drift"), "--json"]
    raw = run_json(command, timeout=30)
    findings: list[dict[str, Any]] = []
    status = raw.get("status")
    if status != "ok":
        findings.append(
            {
                "id": "plugin_drift",
                "severity": "blocking",
                "message": f"Plugin drift checker status is {status!r}.",
            }
        )
    live_sha = raw.get("live_skill", {}).get("sha256") if isinstance(raw.get("live_skill"), dict) else None
    source_sha = (
        raw.get("plugin_source_skill", {}).get("sha256")
        if isinstance(raw.get("plugin_source_skill"), dict)
        else None
    )
    cache_sha = (
        raw.get("plugin_cache_skill", {}).get("sha256")
        if isinstance(raw.get("plugin_cache_skill"), dict)
        else None
    )
    if live_sha and source_sha and cache_sha and len({live_sha, source_sha, cache_sha}) > 1:
        findings.append(
            {
                "id": "plugin_skill_sha_mismatch",
                "severity": "blocking",
                "message": "Live/source/cache Telegram skill SHA values do not all match.",
            }
        )
    source_manifest = load_json(PLUGIN_SOURCE / ".codex-plugin/plugin.json") or {}
    cache_manifest = load_json(PLUGIN_CACHE / ".codex-plugin/plugin.json") or {}
    return {
        "status": status_from_findings(findings),
        "findings": findings,
        "raw_status": status,
        "version": {
            "source": source_manifest.get("version"),
            "cache": cache_manifest.get("version"),
        },
        "artifacts": {
            "live_skill": str(LIVE_SKILL / "SKILL.md"),
            "plugin_source_skill": str(PLUGIN_SOURCE / "skills/telegram/SKILL.md"),
            "plugin_cache_skill": str(PLUGIN_CACHE / "skills/telegram/SKILL.md"),
        },
        "sha256": {
            "live_skill": live_sha or file_sha256(LIVE_SKILL / "SKILL.md"),
            "plugin_source_skill": source_sha or file_sha256(PLUGIN_SOURCE / "skills/telegram/SKILL.md"),
            "plugin_cache_skill": cache_sha or file_sha256(PLUGIN_CACHE / "skills/telegram/SKILL.md"),
        },
        "raw": raw,
    }


def _expected_kind_matches(path: Path, expected_kind: str) -> bool:
    if expected_kind == "directory":
        return path.is_dir()
    if expected_kind == "file":
        return path.is_file()
    if expected_kind == "symlink":
        return path.is_symlink()
    if expected_kind == "path":
        return path.exists()
    return False


def audit_managed_systems() -> dict[str, Any]:
    policy = load_json(POLICY_DIR / "managed-systems.json") or {}
    systems_policy = policy.get("systems") if isinstance(policy.get("systems"), list) else []
    rows: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_paths: set[str] = set()

    for item in systems_policy:
        if not isinstance(item, dict):
            findings.append(
                {
                    "id": "managed_system_policy_item_invalid",
                    "severity": "blocking",
                    "message": "Managed systems policy contains a non-object entry.",
                }
            )
            continue
        system_id = str(item.get("id") or "")
        raw_path = str(item.get("path") or "")
        expected_kind = str(item.get("expected_kind") or "path")
        deletion_protection = str(item.get("deletion_protection") or "blocking")
        required_markers = item.get("required_markers") if isinstance(item.get("required_markers"), list) else []
        path = Path(raw_path) if raw_path else Path()
        exists = bool(raw_path) and path.exists()
        kind_matches = exists and _expected_kind_matches(path, expected_kind)
        missing_markers = sorted(
            str(marker)
            for marker in required_markers
            if isinstance(marker, str) and not (path / marker).exists()
        )
        resolved = str(path.resolve(strict=False)) if raw_path else None
        row = {
            "id": system_id,
            "role": item.get("role"),
            "path": raw_path,
            "expected_kind": expected_kind,
            "exists": exists,
            "kind_matches": kind_matches,
            "missing_markers": missing_markers,
            "resolved": resolved,
            "source_of_truth": bool(item.get("source_of_truth")),
            "deletion_protection": deletion_protection,
            "safe_delete": item.get("safe_delete"),
        }
        rows.append(row)
        if not system_id:
            findings.append(
                {
                    "id": "managed_system_missing_id",
                    "severity": "blocking",
                    "message": "Managed systems policy entry is missing id.",
                }
            )
        elif system_id in seen_ids:
            findings.append(
                {
                    "id": "managed_system_duplicate_id",
                    "severity": "blocking",
                    "system": system_id,
                    "message": "Managed systems policy contains a duplicate id.",
                }
            )
        seen_ids.add(system_id)
        if not raw_path:
            findings.append(
                {
                    "id": "managed_system_missing_path",
                    "severity": "blocking",
                    "system": system_id,
                    "message": "Managed systems policy entry is missing path.",
                }
            )
        elif raw_path in seen_paths:
            findings.append(
                {
                    "id": "managed_system_duplicate_path",
                    "severity": "blocking",
                    "system": system_id,
                    "message": "Managed systems policy contains a duplicate path.",
                }
            )
        seen_paths.add(raw_path)
        if not exists:
            findings.append(
                {
                    "id": "managed_system_missing",
                    "severity": "blocking" if deletion_protection == "blocking" else "warn",
                    "system": system_id,
                    "role": item.get("role"),
                    "path": raw_path,
                    "message": "Registered Telegram managed system path is missing.",
                }
            )
        elif not kind_matches:
            findings.append(
                {
                    "id": "managed_system_kind_mismatch",
                    "severity": "blocking" if deletion_protection == "blocking" else "warn",
                    "system": system_id,
                    "path": raw_path,
                    "expected_kind": expected_kind,
                    "message": "Registered Telegram managed system path exists with the wrong kind.",
                }
            )
        elif missing_markers:
            findings.append(
                {
                    "id": "managed_system_marker_missing",
                    "severity": "blocking" if deletion_protection == "blocking" else "warn",
                    "system": system_id,
                    "path": raw_path,
                    "missing_markers": missing_markers,
                    "message": "Registered Telegram managed system exists but required marker files are missing.",
                }
            )

    deletion_policy = policy.get("deletion_policy") if isinstance(policy.get("deletion_policy"), dict) else {}
    return {
        "status": status_from_findings(findings),
        "findings": findings,
        "systems": rows,
        "deletion_policy": deletion_policy,
        "summary": {
            "registered": len(rows),
            "existing": sum(1 for row in rows if row.get("exists")),
            "blocking_protected": sum(1 for row in rows if row.get("deletion_protection") == "blocking"),
            "missing": sum(1 for row in rows if not row.get("exists")),
            "kind_mismatches": sum(1 for row in rows if row.get("exists") and not row.get("kind_matches")),
            "marker_mismatches": sum(1 for row in rows if row.get("missing_markers")),
        },
    }


def _imported_tool_names(init_py: Path) -> list[str]:
    tree = ast.parse(init_py.read_text(encoding="utf-8"))
    names: list[str] = []
    for node in tree.body:
        if not isinstance(node, ast.ImportFrom):
            continue
        for alias in node.names:
            name = alias.name
            if name == "register" or name.startswith("register_"):
                continue
            names.append(name)
    return sorted(set(names))


def _dialog_annotation_map(dialog_tools_py: Path) -> dict[str, str]:
    text = dialog_tools_py.read_text(encoding="utf-8")
    mapping: dict[str, str] = {}
    pattern = re.compile(r"mcp\.tool\(annotations=(READONLY|ADDITIVE)\)\(tool_error_handler\((\w+)\)\)")
    for annotation, tool_name in pattern.findall(text):
        mapping[tool_name] = annotation.lower()
    return mapping


def _facade_tool_names(init_py: Path) -> set[str]:
    tree = ast.parse(init_py.read_text(encoding="utf-8"))
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id == "FACADE_TOOL_NAMES" for target in node.targets):
            continue
        value = ast.literal_eval(node.value)
        if isinstance(value, set) and all(isinstance(item, str) for item in value):
            return set(value)
    return set()


def audit_mcp_surface() -> dict[str, Any]:
    init_py = MCP_REPO / "src/telegram_mcp/tools/__init__.py"
    dialog_py = MCP_REPO / "src/telegram_mcp/tools/dialog_facade_tools.py"
    tools = _imported_tool_names(init_py) if init_py.exists() else []
    default_surface = sorted(_facade_tool_names(init_py)) if init_py.exists() else []
    effective_default_tools = default_surface or tools
    dialog_annotations = _dialog_annotation_map(dialog_py) if dialog_py.exists() else {}
    unexpected_write = [
        name
        for name in effective_default_tools
        if WRITE_OR_DESTRUCTIVE_RE.search(name) or dialog_annotations.get(name) not in {None, "readonly"}
    ]
    non_facade = [name for name in effective_default_tools if name not in APPROVED_FACADE_TOOLS]
    plugin_mcp = load_json(PLUGIN_SOURCE / ".mcp.json") or {}
    mcp_servers = plugin_mcp.get("mcpServers") if isinstance(plugin_mcp.get("mcpServers"), dict) else {}
    findings: list[dict[str, Any]] = []
    if unexpected_write:
        findings.append(
            {
                "id": "unexpected_write_tools",
                "severity": "blocking",
                "message": "Default MCP endpoint exposes write/destructive tools outside the approved facade.",
                "tools": unexpected_write,
            }
        )
    for name, server in mcp_servers.items():
        if not isinstance(server, dict):
            continue
        allowlist = _server_allowlist(server)
        if allowlist is None:
            findings.append(
                {
                    "id": "mcp_endpoint_without_hard_allowlist",
                    "severity": "blocking",
                    "message": f"MCP server {name!r} has no hard tool allowlist in plugin metadata.",
                }
            )
            continue
        unsafe_tools = sorted(
            tool
            for tool in allowlist
            if tool not in APPROVED_FACADE_TOOLS
            or WRITE_OR_DESTRUCTIVE_RE.search(tool)
            or dialog_annotations.get(tool) not in {None, "readonly"}
        )
        if unsafe_tools:
            findings.append(
                {
                    "id": "mcp_endpoint_unsafe_allowlist_tool",
                    "severity": "blocking",
                    "message": f"MCP server {name!r} allowlist includes tools outside the read-only facade.",
                    "tools": unsafe_tools,
                }
            )
    return {
        "status": status_from_findings(findings),
        "findings": findings,
        "tool_count": len(tools),
        "tools": tools,
        "default_surface_tools": effective_default_tools,
        "approved_facade_tools": sorted(APPROVED_FACADE_TOOLS),
        "unexpected_write_or_destructive_tools": unexpected_write,
        "non_facade_tools": non_facade,
        "dialog_facade_annotations": dialog_annotations,
        "plugin_mcp_servers": mcp_servers,
    }


def _load_plist(path: Path) -> dict[str, Any]:
    try:
        data = plistlib.loads(path.read_bytes())
    except Exception as exc:  # noqa: BLE001 - plist inventory should report parse failures.
        return {"_parse_error": str(exc)}
    return data if isinstance(data, dict) else {"_parse_error": "plist root is not a dictionary"}


def _server_allowlist(server: dict[str, Any]) -> set[str] | None:
    for key in ("allowTools", "allowedTools"):
        value = server.get(key)
        if isinstance(value, list) and all(isinstance(item, str) for item in value):
            return set(value)
    return None


def _launchctl_labels() -> dict[str, dict[str, Any]]:
    try:
        completed = subprocess.run(
            ["launchctl", "list"],
            text=True,
            capture_output=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"_error": {"error": str(exc)}}  # type: ignore[dict-item]
    if completed.returncode != 0:
        return {
            "_error": {
                "error": completed.stderr.strip() or completed.stdout.strip() or "launchctl list failed",
                "exit_code": completed.returncode,
            }
        }  # type: ignore[dict-item]
    labels: dict[str, dict[str, Any]] = {}
    for line in completed.stdout.splitlines():
        parts = line.split()
        if len(parts) < 3:
            continue
        pid, status, label = parts[0], parts[1], parts[2]
        if "telegram" in label or "telecrawl" in label:
            labels[label] = {
                "pid": None if pid == "-" else pid,
                "last_exit_status": status,
                "loaded": True,
            }
    return labels


def _allowed_roots() -> tuple[list[Path], list[Path]]:
    policy = load_json(POLICY_DIR / "allowed-roots.json") or {}
    allowed = [
        Path(str(item.get("path"))).resolve(strict=False)
        for item in policy.get("allowed_roots", [])
        if isinstance(item, dict) and item.get("path")
    ]
    aliases = [
        Path(str(item.get("path"))).resolve(strict=False)
        for item in policy.get("temporary_compatibility_aliases", [])
        if isinstance(item, dict) and item.get("path")
    ]
    return allowed, aliases


def _path_within(path: Path, roots: list[Path]) -> bool:
    resolved = path.resolve(strict=False)
    return any(resolved == root or root in resolved.parents for root in roots)


def _launchd_path_values(data: dict[str, Any]) -> list[str]:
    env = data.get("EnvironmentVariables") if isinstance(data.get("EnvironmentVariables"), dict) else {}
    args = data.get("ProgramArguments") if isinstance(data.get("ProgramArguments"), list) else []
    values = [str(data.get("WorkingDirectory") or ""), str(env.get("PYTHONPATH") or "")]
    values.extend(str(item) for item in args)
    return [value for value in values if value]


def _extract_absolute_paths(value: str) -> list[Path]:
    paths: list[Path] = []
    for part in value.split(":"):
        stripped = part.strip()
        if not stripped.startswith("/") or not PATH_LIKE_RE.search(stripped):
            continue
        paths.append(Path(stripped))
    return paths


def audit_launchd() -> dict[str, Any]:
    launchd_policy = load_json(POLICY_DIR / "launchd-jobs.json") or {}
    allowed_roots, temporary_aliases = _allowed_roots()
    launchctl_only = {
        str(item.get("label"))
        for item in launchd_policy.get("launchctl_only_labels", [])
        if isinstance(item, dict) and item.get("known")
    }
    plists = sorted(LAUNCHAGENTS_DIR.glob("*telegram*.plist")) + sorted(
        LAUNCHAGENTS_DIR.glob("*telecrawl*.plist")
    )
    loaded = _launchctl_labels()
    rows: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    for path in plists:
        data = _load_plist(path)
        label = data.get("Label") if isinstance(data.get("Label"), str) else path.stem
        if "_parse_error" in data:
            findings.append(
                {
                    "id": "launchd_plist_parse_error",
                    "severity": "blocking",
                    "label": label,
                    "plist": str(path),
                    "message": "LaunchAgent plist could not be parsed.",
                    "error": data.get("_parse_error"),
                }
            )
            rows.append({"label": label, "plist": str(path), "parse_error": data.get("_parse_error")})
            continue
        env = data.get("EnvironmentVariables") if isinstance(data.get("EnvironmentVariables"), dict) else {}
        args = data.get("ProgramArguments") if isinstance(data.get("ProgramArguments"), list) else []
        path_values = _launchd_path_values(data)
        uses_legacy_alias = any(str(MIRROR_LEGACY_ALIAS) in value for value in path_values)
        has_secret_env = any(key in env for key in SECRET_ENV_KEYS)
        outside_allowed_roots = sorted(
            str(candidate)
            for value in path_values
            for candidate in _extract_absolute_paths(value)
            if not _path_within(candidate, allowed_roots)
            and not _path_within(candidate, temporary_aliases)
            and not str(candidate).startswith(("/bin", "/usr/bin", "/usr/local/bin", "/opt/homebrew/bin"))
        )
        loaded_state = loaded.get(label, {})
        row = {
            "label": label,
            "plist": str(path),
            "loaded": bool(loaded_state.get("loaded")),
            "pid": loaded_state.get("pid"),
            "working_directory": data.get("WorkingDirectory"),
            "program_arguments": args,
            "pythonpath": env.get("PYTHONPATH"),
            "telegram_session_dir": env.get("TELEGRAM_SESSION_DIR"),
            "telegram_mcp_port": env.get("TELEGRAM_MCP_PORT"),
            "run_at_load": data.get("RunAtLoad"),
            "keep_alive": data.get("KeepAlive"),
            "start_interval": data.get("StartInterval"),
            "uses_legacy_mirror_alias": uses_legacy_alias,
            "has_secret_env": has_secret_env,
            "outside_allowed_roots": outside_allowed_roots,
        }
        rows.append(row)
        if outside_allowed_roots:
            findings.append(
                {
                    "id": "launchd_path_outside_allowed_roots",
                    "severity": "blocking",
                    "label": label,
                    "message": "LaunchAgent references paths outside policy/allowed-roots.json.",
                    "paths": outside_allowed_roots,
                }
            )
        if uses_legacy_alias:
            findings.append(
                {
                    "id": "launchd_legacy_mirror_alias",
                    "severity": "blocking",
                    "label": label,
                    "message": "LaunchAgent references the old telegram-mirror compatibility alias.",
                }
            )
        if label.startswith("com.sereja.telegram-mirror") and (data.get("RunAtLoad") or data.get("KeepAlive")):
            findings.append(
                {
                    "id": "mirror_launchagent_autostart_configured",
                    "severity": "blocking",
                    "label": label,
                    "message": "Mirror LaunchAgent has RunAtLoad/KeepAlive configured while mirror is recovery-scoped.",
                }
            )
        if has_secret_env:
            findings.append(
                {
                    "id": "launchd_secret_snapshot",
                    "severity": "warn",
                    "label": label,
                    "message": "LaunchAgent contains Telegram secret environment values; registry must not copy them.",
                }
            )
    for label, state in loaded.items():
        if label == "_error":
            findings.append(
                {
                    "id": "launchctl_list_failed",
                    "severity": "blocking",
                    "message": state.get("error"),
                    "exit_code": state.get("exit_code"),
                }
            )
            continue
        if not any(row["label"] == label for row in rows):
            if label in launchctl_only:
                continue
            findings.append(
                {
                    "id": "loaded_job_without_plist_inventory",
                    "severity": "blocking",
                    "label": label,
                    "message": "launchctl reports a Telegram/telecrawl job not found in plist inventory.",
                }
            )
    return {
        "status": status_from_findings(findings),
        "findings": findings,
        "jobs": rows,
        "loaded_jobs": loaded,
        "policy": launchd_policy,
    }


def audit_mcp_profiles() -> dict[str, Any]:
    launchd = audit_launchd()
    profiles = []
    findings: list[dict[str, Any]] = []
    for row in launchd["jobs"]:
        label = row.get("label")
        if label not in {"com.sereja.telegram-mcp-http", "com.sereja.telegram-mcp-http-pl"}:
            continue
        profiles.append(
            {
                "label": label,
                "port": row.get("telegram_mcp_port"),
                "session_dir": row.get("telegram_session_dir") or "/Users/sereja/.telegram-mcp/session",
                "working_directory": row.get("working_directory"),
                "loaded": row.get("loaded"),
                "write_policy": "unrestricted_server_surface_until_allowlisted",
            }
        )
    if len(profiles) < 2:
        findings.append(
            {
                "id": "mcp_profile_map_incomplete",
                "severity": "warn",
                "message": "Expected main and pl MCP profiles in launchd inventory.",
            }
        )
    return {"status": status_from_findings(findings), "findings": findings, "profiles": profiles}


def audit_sessions() -> dict[str, Any]:
    session_policy = load_json(POLICY_DIR / "sessions.json") or {}
    registered = {
        str(item.get("path")): item
        for item in session_policy.get("sessions", [])
        if isinstance(item, dict) and item.get("path")
    }
    candidates = [
        Path("/Users/sereja/.telegram-mcp/session.session"),
        Path("/Users/sereja/.telegram-mcp-pl/session.session"),
    ]
    candidates.extend(sorted(MIRROR_ROOT.glob("data/*.session")))
    sessions: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    for path in candidates:
        exists = path.exists()
        owner = "mirror_recovery_tree" if MIRROR_ROOT in path.parents else "live_mcp_profile"
        policy = registered.get(str(path))
        sessions.append(
            {
                "path": str(path),
                "exists": exists,
                "owner_guess": owner,
                "registered": policy is not None,
                "runtime_allowed": policy.get("runtime_allowed") if isinstance(policy, dict) else None,
                "account_key": policy.get("account_key") if isinstance(policy, dict) else None,
                "size_bytes": path.stat().st_size if exists and path.is_file() else None,
                "schema_checked": False,
                "lease_checked": False,
            }
        )
        if exists and policy is None:
            findings.append(
                {
                    "id": "unregistered_session",
                    "severity": "blocking",
                    "path": str(path),
                    "message": "Telegram session exists but is not covered by policy/sessions.json.",
                }
            )
        if exists and owner == "mirror_recovery_tree" and isinstance(policy, dict) and policy.get("runtime_allowed"):
            findings.append(
                {
                    "id": "mirror_recovery_session_runtime_allowed",
                    "severity": "blocking",
                    "path": str(path),
                    "message": "Mirror recovery session is marked runtime_allowed.",
                }
            )
    return {
        "status": status_from_findings(findings),
        "findings": findings,
        "sessions": sessions,
        "policy": session_policy,
    }


def audit_mirror() -> dict[str, Any]:
    mirror_policy = load_json(POLICY_DIR / "mirror.json") or {}
    recovery_mode = mirror_policy.get("classification") == "mirror-recovery"
    recovery_docs = {
        "AGENTS.md": MIRROR_ROOT / "AGENTS.md",
        "RECOVERY.md": MIRROR_ROOT / "RECOVERY.md",
        "PROVENANCE.md": MIRROR_ROOT / "PROVENANCE.md",
    }
    sessions = sorted(str(path) for path in MIRROR_ROOT.glob("data/*.session*"))
    ledgers = sorted(str(path) for path in (MIRROR_ROOT / "data/telegram_sync").glob("*.json"))
    runtime_exports = MIRROR_ROOT / "runtime/ingest/telegram/exports"
    legacy_alias_exists = MIRROR_LEGACY_ALIAS.exists()
    findings: list[dict[str, Any]] = []
    if not (MIRROR_ROOT / ".git").exists():
        findings.append(
            {
                "id": "mirror_not_git_repo",
                "severity": "warn" if recovery_mode else "blocking",
                "message": "telegram-mirror is not a clean git source repo.",
            }
        )
    if sessions:
        findings.append(
            {
                "id": "mirror_runtime_sessions_in_tree",
                "severity": "warn" if recovery_mode else "blocking",
                "message": "Session files exist inside telegram-mirror recovery tree.",
                "count": len(sessions),
            }
        )
    if not runtime_exports.exists():
        findings.append(
            {
                "id": "mirror_runtime_exports_missing",
                "severity": "warn" if recovery_mode else "blocking",
                "message": "Canonical mirror runtime export root is missing.",
            }
        )
    return {
        "status": status_from_findings(findings),
        "classification": mirror_policy.get("classification") or "mirror-recovery",
        "findings": findings,
        "policy": mirror_policy,
        "root": str(MIRROR_ROOT),
        "legacy_alias": {
            "path": str(MIRROR_LEGACY_ALIAS),
            "exists": legacy_alias_exists,
            "resolved": str(MIRROR_LEGACY_ALIAS.resolve()) if legacy_alias_exists else None,
        },
        "recovery_docs": {name: {"path": str(path), "exists": path.exists()} for name, path in recovery_docs.items()},
        "runtime_state": {
            "sessions": sessions,
            "ledgers": ledgers,
            "runtime_exports_exists": runtime_exports.exists(),
        },
    }


def audit_mirror_preflight() -> dict[str, Any]:
    """Promotion preflight for moving telegram-mirror out of recovery mode."""

    mirror = audit_mirror()
    allowlist_report = run_json(
        ["python3", str(MIRROR_ROOT / "scripts/telegram_mirror_allowlist_report.py"), "--json"],
        timeout=30,
    )
    launchd = audit_launchd()
    session_report = audit_sessions()
    runtime_exports = MIRROR_ROOT / "runtime/ingest/telegram/exports"
    venv_python = MIRROR_ROOT / ".venv/bin/python"
    ledgers = mirror.get("runtime_state", {}).get("ledgers")
    sessions = mirror.get("runtime_state", {}).get("sessions")
    loaded_jobs = launchd.get("loaded_jobs") if isinstance(launchd.get("loaded_jobs"), dict) else {}
    loaded_mirror_jobs = sorted(
        label
        for label, state in loaded_jobs.items()
        if isinstance(label, str)
        and label.startswith("com.sereja.telegram")
        and "mcp" not in label
        and isinstance(state, dict)
        and state.get("loaded")
    )

    gates = [
        {
            "id": "source_boundary",
            "status": "ok" if (MIRROR_ROOT / ".git").exists() else "fail",
            "message": "telegram-mirror must be a clean source repo or have an explicit non-git source boundary.",
            "evidence": {"git_dir_exists": (MIRROR_ROOT / ".git").exists()},
        },
        {
            "id": "runtime_environment",
            "status": "ok" if venv_python.exists() else "fail",
            "message": "Runtime promotion needs a pinned local Python environment.",
            "evidence": {"venv_python": str(venv_python), "exists": venv_python.exists()},
        },
        {
            "id": "explicit_allowlist",
            "status": "ok" if allowlist_report.get("policy_exists") else "fail",
            "message": "Promotion needs an explicit retention/runtime allowlist, not only enabled channel config.",
            "evidence": {
                "policy_source": allowlist_report.get("policy_source"),
                "policy_exists": allowlist_report.get("policy_exists"),
                "channel_count": allowlist_report.get("channel_count"),
                "retained_channel_count": allowlist_report.get("retained_channel_count"),
            },
        },
        {
            "id": "mirror_registry",
            "status": "ok"
            if (allowlist_report.get("registry") or {}).get("mirrors_count")
            else "fail",
            "message": "Promotion needs a mirror registry with source to mirror mappings.",
            "evidence": allowlist_report.get("registry"),
        },
        {
            "id": "session_externalization",
            "status": "ok" if not sessions else "fail",
            "message": "Runtime sessions must be owned outside the recovery source tree before promotion.",
            "evidence": {"session_count_in_tree": len(sessions) if isinstance(sessions, list) else None},
        },
        {
            "id": "runtime_exports",
            "status": "ok" if runtime_exports.exists() else "fail",
            "message": "Canonical runtime export root must exist before runtime claims are allowed.",
            "evidence": {"path": str(runtime_exports), "exists": runtime_exports.exists()},
        },
        {
            "id": "launchd_cold_mode",
            "status": "ok" if not loaded_mirror_jobs else "fail",
            "message": "No mirror watcher/backfill LaunchAgents should be loaded before promotion.",
            "evidence": {"loaded_mirror_jobs": loaded_mirror_jobs},
        },
        {
            "id": "ledger_inventory",
            "status": "ok" if ledgers else "fail",
            "message": "Recovered progress ledgers must be inventoried before promotion.",
            "evidence": {"ledger_count": len(ledgers) if isinstance(ledgers, list) else None},
        },
        {
            "id": "session_registry_policy",
            "status": "ok" if session_report.get("status") == "ok" else "fail",
            "message": "All discovered Telegram sessions must be covered by policy/sessions.json.",
            "evidence": {"session_audit_status": session_report.get("status")},
        },
    ]
    findings = [
        {
            "id": gate["id"],
            "severity": "blocking",
            "message": gate["message"],
            "evidence": gate.get("evidence"),
        }
        for gate in gates
        if gate.get("status") != "ok"
    ]
    return {
        "status": status_from_findings(findings),
        "findings": findings,
        "classification": mirror.get("classification"),
        "promotion_allowed": not findings,
        "gates": gates,
        "freshness_probe": {
            "required_before_promotion": True,
            "note": "Run scripts/prime_mirror_readonly_probe.py with an explicit session and env; do not start watchers.",
        },
        "inputs": {
            "mirror_audit": mirror,
            "allowlist_report": allowlist_report,
        },
    }


def _safe_read_telecrawl_json(args: list[str], *, timeout: int = 90) -> dict[str, Any]:
    if not TELECRAWL_ARCHIVE.exists():
        return {"ok": False, "error": "missing_telecrawl_archive_wrapper", "path": str(TELECRAWL_ARCHIVE)}
    return run_json([str(TELECRAWL_ARCHIVE), *args], timeout=timeout)


def audit_telecrawl() -> dict[str, Any]:
    telecrawl_policy = load_json(POLICY_DIR / "telecrawl.json") or {}
    accounts = _safe_read_telecrawl_json(["accounts"], timeout=30)
    status = _safe_read_telecrawl_json(["status"], timeout=90)
    findings: list[dict[str, Any]] = []
    account_rows = accounts.get("accounts") if isinstance(accounts.get("accounts"), list) else []
    inactive = [row for row in account_rows if not row.get("active")]
    if inactive:
        findings.append(
            {
                "id": "telecrawl_inactive_accounts",
                "severity": "warn",
                "message": "Telecrawl account catalog contains inactive or missing archive accounts.",
                "count": len(inactive),
            }
        )
    import_gaps = status.get("import_gaps") if isinstance(status.get("import_gaps"), dict) else {}
    if import_gaps.get("has_known_gaps"):
        severity = (
            "warn"
            if telecrawl_policy.get("known_gaps_are_blocking_for_archive_search") is False
            else "blocking"
        )
        findings.append(
            {
                "id": "telecrawl_known_gaps",
                "severity": severity,
                "message": "Telecrawl default archive has known import gaps.",
                "summary": import_gaps.get("error_summary"),
            }
        )
    if status.get("source_kind") != "archive_snapshot":
        findings.append(
            {
                "id": "telecrawl_source_kind_unexpected",
                "severity": "warn",
                "message": "Telecrawl status did not report archive_snapshot source kind.",
            }
        )
    return {
        "status": status_from_findings(findings),
        "findings": findings,
        "wrapper": str(TELECRAWL_ARCHIVE),
        "policy": telecrawl_policy,
        "accounts": accounts,
        "default_archive_status": status,
        "freshness": {
            "last_complete_import_at": status.get("last_complete_import_at"),
            "newest_message_at": status.get("status", {}).get("newest_message")
            if isinstance(status.get("status"), dict)
            else status.get("newest_message_at"),
            "generated_at": status.get("generated_at"),
        },
    }


def _collect_components() -> dict[str, dict[str, Any]]:
    return {
        "managed_systems": audit_managed_systems(),
        "plugin_drift": audit_plugin_drift(),
        "mcp_surface": audit_mcp_surface(),
        "mcp_profiles": audit_mcp_profiles(),
        "launchd": audit_launchd(),
        "sessions": audit_sessions(),
        "telegram_mirror": audit_mirror(),
        "telecrawl": audit_telecrawl(),
    }


def build_registry() -> dict[str, Any]:
    raw_components = _collect_components()
    findings: list[dict[str, Any]] = []
    for component, report in raw_components.items():
        for item in report.get("findings", []):
            enriched = dict(item)
            enriched.setdefault("component", component)
            findings.append(enriched)
    components = {
        name: _project_registry_component(name, report)
        for name, report in raw_components.items()
    }
    registry = {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "read_only_external_state": True,
        "status": status_from_findings(findings),
        "summary": {
            "components": {name: report.get("status") for name, report in raw_components.items()},
            "blocking_findings": sum(1 for item in findings if item.get("severity") == "blocking"),
            "warning_findings": sum(1 for item in findings if item.get("severity") in {"warn", "warning"}),
        },
        "findings": findings,
        "components": components,
    }
    return _redact_private_runtime_details(registry)


def write_registry(path: Path, registry: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(registry, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _project_registry_component(name: str, report: dict[str, Any]) -> dict[str, Any]:
    enriched = _registry_component_enriched(name, report)
    schema = load_json(POLICY_DIR / "registry-schema.json") or {}
    fields_by_component = schema.get("component_fields") if isinstance(schema.get("component_fields"), dict) else {}
    fields = fields_by_component.get(name)
    if not isinstance(fields, list) or not all(isinstance(field, str) for field in fields):
        fields = ["status", "findings"]
    return {field: enriched[field] for field in fields if field in enriched}


def _registry_component_enriched(name: str, report: dict[str, Any]) -> dict[str, Any]:
    if name == "sessions":
        sessions = report.get("sessions") if isinstance(report.get("sessions"), list) else []
        policy = report.get("policy") if isinstance(report.get("policy"), dict) else {}
        registered_policy = policy.get("sessions") if isinstance(policy.get("sessions"), list) else []
        return {
            "status": report.get("status"),
            "findings": report.get("findings", []),
            "summary": {
                "discovered": len(sessions),
                "existing": sum(1 for item in sessions if isinstance(item, dict) and item.get("exists")),
                "registered": sum(1 for item in sessions if isinstance(item, dict) and item.get("registered")),
                "runtime_allowed": sum(
                    1 for item in sessions if isinstance(item, dict) and item.get("runtime_allowed")
                ),
                "schema_checked": sum(1 for item in sessions if isinstance(item, dict) and item.get("schema_checked")),
                "lease_checked": sum(1 for item in sessions if isinstance(item, dict) and item.get("lease_checked")),
            },
            "policy_summary": {
                "registered": len(registered_policy),
                "runtime_allowed": sum(
                    1 for item in registered_policy if isinstance(item, dict) and item.get("runtime_allowed")
                ),
                "recovery_runtime_allowed": sum(
                    1
                    for item in registered_policy
                    if isinstance(item, dict)
                    and str(item.get("owner", "")).startswith("telegram-mirror")
                    and item.get("runtime_allowed")
                ),
            },
        }
    if name == "telegram_mirror":
        runtime_state = report.get("runtime_state") if isinstance(report.get("runtime_state"), dict) else {}
        sessions = runtime_state.get("sessions") if isinstance(runtime_state.get("sessions"), list) else []
        ledgers = runtime_state.get("ledgers") if isinstance(runtime_state.get("ledgers"), list) else []
        return {
            **report,
            "runtime_state_summary": {
                "session_count": len(sessions),
                "ledger_count": len(ledgers),
                "runtime_exports_exists": bool(runtime_state.get("runtime_exports_exists")),
            },
        }
    if name == "telecrawl":
        accounts_payload = report.get("accounts") if isinstance(report.get("accounts"), dict) else {}
        accounts = accounts_payload.get("accounts") if isinstance(accounts_payload.get("accounts"), list) else []
        archive = report.get("default_archive_status") if isinstance(report.get("default_archive_status"), dict) else {}
        return {
            **report,
            "account_summary": {
                "total": len(accounts),
                "active": sum(1 for item in accounts if isinstance(item, dict) and item.get("active")),
                "inactive": sum(1 for item in accounts if isinstance(item, dict) and not item.get("active")),
                "archive_ready": bool(archive.get("archive_ready")),
                "known_gap_count": (
                    archive.get("import_gaps", {}).get("errors")
                    if isinstance(archive.get("import_gaps"), dict)
                    else None
                ),
            },
        }
    if name == "mcp_profiles":
        profiles = report.get("profiles") if isinstance(report.get("profiles"), list) else []
        safe_profiles = []
        for profile in profiles:
            if not isinstance(profile, dict):
                continue
            safe_profiles.append(
                {
                    "label": profile.get("label"),
                    "port": profile.get("port"),
                    "loaded": profile.get("loaded"),
                    "write_policy": profile.get("write_policy"),
                }
            )
        return {**report, "profiles": safe_profiles}
    return dict(report)


def _redact_private_runtime_details(value: Any) -> Any:
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if key in PRIVATE_KEYS:
                if key == "path" and isinstance(item, str) and not any(
                    marker in item for marker in PRIVATE_PATH_SUBSTRINGS
                ):
                    result[key] = item
                continue
            else:
                result[key] = _redact_private_runtime_details(item)
        return result
    if isinstance(value, list):
        return [_redact_private_runtime_details(item) for item in value]
    if isinstance(value, str) and any(marker in value for marker in PRIVATE_PATH_SUBSTRINGS):
        return "<redacted>"
    if isinstance(value, str) and (value.startswith("tg:") or value.startswith("Telegram @")):
        return "<redacted>"
    return copy.deepcopy(value)


def _redacted_private_value(key: str, value: Any) -> Any:
    if key == "path" and isinstance(value, str) and not any(marker in value for marker in PRIVATE_PATH_SUBSTRINGS):
        return value
    if isinstance(value, bool) or value is None:
        return value
    return "<redacted>"
