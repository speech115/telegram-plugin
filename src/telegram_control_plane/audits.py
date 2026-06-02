from __future__ import annotations

import ast
import copy
import json
import plistlib
import re
import sqlite3
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .paths import (
    CONTROL_ROOT,
    FAST_READ_ADAPTER,
    LAUNCHAGENTS_DIR,
    LIVE_SKILL,
    MCP_REPO,
    MCP_TELEMETRY_LOG,
    MCP_TELEMETRY_STATS,
    MIRROR_LEGACY_ALIAS,
    MIRROR_ROOT,
    MIRROR_RUNTIME_ROOT,
    POLICY_DIR,
    PLUGIN_CACHE,
    PLUGIN_CACHE_ROOT,
    PLUGIN_PACKAGE,
    PLUGIN_SOURCE,
    TELECRAWL_ARCHIVE,
    TELECRAWL_DEFAULT_DB,
    plugin_source_version,
)
from .util import load_json, run_json, status_from_findings


APPROVED_FACADE_TOOLS = {
    "doctor_check",
    "get_me",
    "resolve_dialog",
    "find_dialog",
    "collect_dialog_context",
    "collect_context",
    "prepare_dialog_reply",
    "draft_reply",
    "prepare_send_message",
    "prepare_reply_message",
    "prepare_media_inspection_manifest",
    "download_media",
    "download_media_batch",
    "download_dialog_media",
    "telegram_inspect_media",
    "telegram_confirmed_send",
    "telegram_export_members",
    "telegram_prepare_reply",
    "telegram_read",
    "telegram_search",
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

DEFAULT_NON_RETRYABLE_TELECRAWL_ERRORS = frozenset(
    {
        "ChannelPrivateError",
        "ChatAdminRequiredError",
        "UserBannedInChannelError",
        "UserNotParticipantError",
        "ChannelInvalidError",
        "InviteHashExpiredError",
        "InviteHashInvalidError",
    }
)


def audit_plugin_drift() -> dict[str, Any]:
    command = [str(MCP_REPO / "bin/check-plugin-drift"), "--json"]
    raw = run_json(command, timeout=30)
    findings: list[dict[str, Any]] = []
    status = raw.get("status")
    installer_flow = raw.get("installer_flow") if isinstance(raw.get("installer_flow"), dict) else {}
    installer_ready = status == "installer_ready_drift" and installer_flow.get("safe_to_apply") is True
    if status != "ok" and not installer_ready:
        findings.append(
            {
                "id": "plugin_drift",
                "severity": "blocking",
                "message": f"Plugin drift checker status is {status!r}.",
            }
        )
    elif installer_ready:
        findings.append(
            {
                "id": "plugin_cache_needs_materialization",
                "severity": "warn",
                "message": (
                    "Plugin source is ahead of installed cache; run the Codex installer flow "
                    "before treating cache as current."
                ),
                "installer_command": installer_flow.get("command"),
                "materialize_command": installer_flow.get("materialize_command"),
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
            "live_skill": _raw_sha(raw, "live_skill"),
            "plugin_source_skill": _raw_sha(raw, "plugin_source_skill"),
            "plugin_cache_skill": _raw_sha(raw, "plugin_cache_skill"),
        },
        "tree_sha256": {
            "live_skill_tree": _raw_tree_sha(raw, "live_skill_tree"),
            "plugin_source_skill_tree": _raw_tree_sha(raw, "plugin_source_skill_tree"),
            "plugin_cache_skill_tree": _raw_tree_sha(raw, "plugin_cache_skill_tree"),
            "plugin_source_package": _raw_tree_sha(raw, "plugin_source_package_tree"),
            "plugin_cache_package": _raw_tree_sha(raw, "plugin_cache_package_tree"),
        },
        "tree_file_counts": {
            "live_skill_tree": _raw_tree_file_count(raw, "live_skill_tree"),
            "plugin_source_skill_tree": _raw_tree_file_count(raw, "plugin_source_skill_tree"),
            "plugin_cache_skill_tree": _raw_tree_file_count(raw, "plugin_cache_skill_tree"),
            "plugin_source_package": _raw_tree_file_count(raw, "plugin_source_package_tree"),
            "plugin_cache_package": _raw_tree_file_count(raw, "plugin_cache_package_tree"),
        },
        "tree_diff": raw.get("tree_diff") if isinstance(raw.get("tree_diff"), dict) else {},
        "raw": raw,
    }


def audit_mcp_telemetry(*, window_hours: float = 24.0) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    python_bin = MCP_REPO / ".venv/bin/python"
    log_path = Path(MCP_TELEMETRY_LOG)

    summary: dict[str, Any]
    if log_path.exists() and python_bin.exists():
        summary = run_json(
            [
                str(python_bin),
                "-m",
                "telegram_mcp.telemetry",
                "--summarize",
                "--json",
                "--log-path",
                str(log_path),
                "--window-hours",
                str(window_hours),
            ],
            timeout=60,
        )
    else:
        summary = {
            "status": "missing",
            "log_path": str(log_path),
            "events_in_window": 0,
        }

    summary_status = summary.get("status")
    events_in_window = int(summary.get("events_in_window") or 0)
    tool_errors = int(summary.get("tool_errors") or 0)

    if summary_status == "missing":
        findings.append(
            {
                "id": "telemetry_log_missing",
                "severity": "warn",
                "message": (
                    "MCP telemetry log is not present yet. Restart HTTP MCP with "
                    "TELEGRAM_TELEMETRY_ENABLED=true (default) to begin collecting events."
                ),
            }
        )
    elif summary_status == "ok" and events_in_window == 0:
        findings.append(
            {
                "id": "telemetry_no_recent_events",
                "severity": "warn",
                "message": (
                    f"No telemetry events in the last {window_hours:g}h. "
                    "Confirm MCP HTTP daemons are running and receiving tool traffic."
                ),
            }
        )
    elif tool_errors >= 10:
        findings.append(
            {
                "id": "telemetry_high_tool_error_rate",
                "severity": "warn",
                "message": f"MCP telemetry recorded {tool_errors} tool errors in the recent window.",
            }
        )

    cache = summary.get("cache") if isinstance(summary.get("cache"), dict) else {}
    return {
        "status": status_from_findings(findings),
        "findings": findings,
        "summary": summary,
        "artifacts": {
            "telemetry_log": str(log_path),
            "telemetry_stats": str(MCP_TELEMETRY_STATS),
        },
        "stats_file_present": MCP_TELEMETRY_STATS.exists(),
        "events_in_window": events_in_window,
        "tool_errors": tool_errors,
        "cache_hit_rate": cache.get("hit_rate"),
    }


DOC_AUDIT_PATHS = (
    CONTROL_ROOT / "README.md",
    CONTROL_ROOT / "PLAN.md",
)
DOC_PLUGIN_VERSION_RE = re.compile(r"plugin version `(\d+\.\d+\.\d+)`")
DEPRECATED_DEFAULT_SURFACE_DOC_TOOLS = frozenset({"list_chats"})


def audit_docs() -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    plugin_version = plugin_source_version()
    checked: list[str] = []

    for path in DOC_AUDIT_PATHS:
        if not path.exists():
            findings.append(
                {
                    "id": "docs_missing",
                    "severity": "blocking",
                    "message": f"Expected control-plane doc is missing: {path.name}",
                    "path": str(path),
                }
            )
            continue
        checked.append(str(path))
        text = path.read_text(encoding="utf-8")
        for match in DOC_PLUGIN_VERSION_RE.finditer(text):
            mentioned = match.group(1)
            if plugin_version and mentioned != plugin_version:
                findings.append(
                    {
                        "id": "stale_plugin_version_in_docs",
                        "severity": "blocking",
                        "message": (
                            f"{path.name} mentions plugin version {mentioned!r}; "
                            f"canonical package version is {plugin_version!r}."
                        ),
                        "path": str(path),
                        "mentioned_version": mentioned,
                        "expected_version": plugin_version,
                    }
                )
        for tool in sorted(DEPRECATED_DEFAULT_SURFACE_DOC_TOOLS):
            if tool in text:
                findings.append(
                    {
                        "id": "deprecated_default_surface_tool_in_docs",
                        "severity": "blocking",
                        "message": (
                            f"{path.name} documents deprecated default-surface tool {tool!r}; "
                            "update examples to facade tools."
                        ),
                        "path": str(path),
                        "tool": tool,
                    }
                )

    return {
        "status": status_from_findings(findings),
        "findings": findings,
        "checked_paths": checked,
        "plugin_version": plugin_version,
        "deprecated_default_surface_tools": sorted(DEPRECATED_DEFAULT_SURFACE_DOC_TOOLS),
    }


def _raw_sha(raw: dict[str, Any], key: str) -> str | None:
    item = raw.get(key)
    if not isinstance(item, dict):
        return None
    value = item.get("sha256")
    return value if isinstance(value, str) else None


def _raw_tree_sha(raw: dict[str, Any], key: str) -> str | None:
    item = raw.get(key)
    if not isinstance(item, dict):
        return None
    value = item.get("sha256")
    return value if isinstance(value, str) else None


def _raw_tree_file_count(raw: dict[str, Any], key: str) -> int | None:
    item = raw.get(key)
    if not isinstance(item, dict):
        return None
    value = item.get("file_count")
    return value if isinstance(value, int) else None


def audit_fast_read_adapter() -> dict[str, Any]:
    """Verify the local read-only fast path used before mcporter for simple reads."""

    exists = FAST_READ_ADAPTER.is_file()
    executable = exists and FAST_READ_ADAPTER.stat().st_mode & 0o111 != 0
    command = [str(FAST_READ_ADAPTER), "--help"]
    help_probe: dict[str, Any] = {"ran": False}
    findings: list[dict[str, Any]] = []

    if not exists:
        findings.append(
            {
                "id": "fast_read_adapter_missing",
                "severity": "blocking",
                "message": "telegram-fast-read-today adapter is missing.",
            }
        )
    elif not executable:
        findings.append(
            {
                "id": "fast_read_adapter_not_executable",
                "severity": "blocking",
                "message": "telegram-fast-read-today adapter exists but is not executable.",
            }
        )
    else:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        help_probe = {
            "ran": True,
            "exit_code": completed.returncode,
            "stdout_contains_usage": "telegram-fast-read-today" in completed.stdout,
        }
        if completed.returncode != 0 or "telegram-fast-read-today" not in completed.stdout:
            findings.append(
                {
                    "id": "fast_read_adapter_help_failed",
                    "severity": "blocking",
                    "message": "telegram-fast-read-today --help did not return the expected CLI contract.",
                }
            )
        adapter_source = FAST_READ_ADAPTER.read_text(encoding="utf-8", errors="replace")
        module_path = MCP_REPO / "src/telegram_mcp/fast_read_today.py"
        module_source = (
            module_path.read_text(encoding="utf-8", errors="replace")
            if module_path.is_file()
            else ""
        )
        if "telegram_mcp.fast_read_today" not in adapter_source:
            findings.append(
                {
                    "id": "fast_read_adapter_wrapper_drift",
                    "severity": "blocking",
                    "message": "telegram-fast-read-today must delegate to telegram_mcp.fast_read_today.",
                }
            )
        if '"telegram_read"' not in module_source:
            findings.append(
                {
                    "id": "fast_read_adapter_stale_tool",
                    "severity": "blocking",
                    "message": (
                        "telegram_mcp.fast_read_today must call the task-shaped "
                        "telegram_read tool exposed on the default MCP surface."
                    ),
                }
            )
        if '"read_today_dialog"' in module_source:
            findings.append(
                {
                    "id": "fast_read_adapter_legacy_tool",
                    "severity": "blocking",
                    "message": (
                        "telegram_mcp.fast_read_today still references read_today_dialog, "
                        "which is not on the default plugin allowlist."
                    ),
                }
            )

    return {
        "status": status_from_findings(findings),
        "findings": findings,
        "adapter": {
            "path": str(FAST_READ_ADAPTER),
            "exists": exists,
            "executable": bool(executable),
            "command": command,
            "help_probe": help_probe,
        },
        "routing": {
            "first_path_for": ["simple_today_read"],
            "fallback": "live_mcp_facade",
            "never_for": ["send", "reply", "media_inspection", "subscriber_export"],
        },
    }


def audit_agent_docs_sync() -> dict[str, Any]:
    """Ensure MCP docs/agent matches plugin references manifest."""

    command = [
        str(MCP_REPO / "bin/sync-agent-docs"),
        "--plugin-dir",
        str(PLUGIN_PACKAGE),
        "--check",
        "--no-restart",
        "--json",
    ]
    raw = run_json(command, timeout=30)
    findings: list[dict[str, Any]] = []
    if raw.get("status") == "drift":
        for item in raw.get("drift", []):
            findings.append(
                {
                    "id": "agent_docs_drift",
                    "severity": "blocking",
                    "message": str(item),
                }
            )
    elif raw.get("status") not in {"ok", None}:
        findings.append(
            {
                "id": "agent_docs_sync_failed",
                "severity": "blocking",
                "message": f"agent docs sync check status is {raw.get('status')!r}.",
            }
        )
    return {
        "status": status_from_findings(findings),
        "findings": findings,
        "command": command,
        "topics": raw.get("topics"),
        "drift": raw.get("drift"),
    }


def audit_release_gates() -> dict[str, Any]:
    """Packaging hygiene, fresh-install adapter smoke, and prompt-safety heuristics."""

    command = [
        str(MCP_REPO / "bin/check-release-gates"),
        "--package-dir",
        str(PLUGIN_PACKAGE),
        "--plugin-dir",
        str(PLUGIN_PACKAGE),
        "--json",
    ]
    raw = run_json(command, timeout=60)
    findings: list[dict[str, Any]] = []
    if raw.get("exit_code") not in {0, None} and raw.get("status") is None:
        findings.append(
            {
                "id": "release_gates_command_failed",
                "severity": "blocking",
                "message": "telegram-mcp release gate command failed.",
                "command": command,
                "stderr": raw.get("stderr"),
            }
        )
        return {
            "status": status_from_findings(findings),
            "findings": findings,
            "command": command,
        }

    if raw.get("status") != "ok":
        for gate in raw.get("gates", []):
            if not isinstance(gate, dict) or gate.get("status") == "ok":
                continue
            for issue in gate.get("findings", []):
                findings.append(
                    {
                        "id": f"release_gate_{gate.get('name', 'unknown')}",
                        "severity": "blocking",
                        "message": str(issue),
                    }
                )
        if not findings:
            findings.append(
                {
                    "id": "release_gates_failed",
                    "severity": "blocking",
                    "message": "Release gates reported failure without details.",
                }
            )

    return {
        "status": status_from_findings(findings),
        "findings": findings,
        "command": command,
        "gates": raw.get("gates", []),
        "failed": raw.get("failed", []),
    }


def audit_install_adapters() -> dict[str, Any]:
    """Dry-run host adapter generation must stay portable."""

    command = [str(MCP_REPO / "bin/install-adapters"), "--host", "all", "--json"]
    raw = run_json(command, timeout=30)
    findings: list[dict[str, Any]] = []
    if raw.get("status") != "ok":
        findings.append(
            {
                "id": "install_adapters_plan_failed",
                "severity": "blocking",
                "message": "Adapter installer returned non-ok status.",
            }
        )
    planned = raw.get("planned_files", [])
    for item in planned:
        if not isinstance(item, dict):
            continue
        content = item.get("content", "")
        if isinstance(content, str) and "/Users/sereja" in content:
            findings.append(
                {
                    "id": "install_adapters_private_path",
                    "severity": "blocking",
                    "message": f"Adapter plan contains a hardcoded private path: {item.get('path')}",
                }
            )

    return {
        "status": status_from_findings(findings),
        "findings": findings,
        "command": command,
        "hosts": raw.get("hosts", []),
        "planned_files": len(planned) if isinstance(planned, list) else 0,
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


def _policy_marker(marker: str) -> str:
    source_manifest = load_json(PLUGIN_SOURCE / ".codex-plugin/plugin.json") or {}
    source_version = source_manifest.get("version")
    cache_version = PLUGIN_CACHE.name if PLUGIN_CACHE.parent == PLUGIN_CACHE_ROOT else ""
    version = source_version if isinstance(source_version, str) and source_version else cache_version
    return marker.replace("{plugin_source_version}", version)


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
        expected_resolved = item.get("expected_resolved") if isinstance(item.get("expected_resolved"), str) else None
        path = Path(raw_path) if raw_path else Path()
        exists = bool(raw_path) and path.exists()
        kind_matches = exists and _expected_kind_matches(path, expected_kind)
        missing_markers = sorted(
            str(marker)
            for marker in required_markers
            if isinstance(marker, str) and not (path / _policy_marker(marker)).exists()
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
        if expected_resolved:
            row["expected_resolved"] = expected_resolved
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
        elif expected_resolved and resolved != expected_resolved:
            findings.append(
                {
                    "id": "managed_system_resolved_target_mismatch",
                    "severity": "blocking" if deletion_protection == "blocking" else "warn",
                    "system": system_id,
                    "path": raw_path,
                    "resolved": resolved,
                    "expected_resolved": expected_resolved,
                    "message": "Registered Telegram managed system resolves to an unexpected target.",
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


def _confirmed_write_facade_tools() -> set[str]:
    policy = load_json(POLICY_DIR / "write-policy.json") or {}
    default_profile = policy.get("default_mcp_profile")
    if not isinstance(default_profile, dict):
        return set()
    tools = default_profile.get("confirmed_write_facade_tools")
    if not isinstance(tools, list):
        return set()
    return {str(item) for item in tools if isinstance(item, str)}


def _is_unexpected_default_surface_tool(name: str, dialog_annotations: dict[str, str]) -> bool:
    if name in _confirmed_write_facade_tools():
        return False
    if WRITE_OR_DESTRUCTIVE_RE.search(name):
        return True
    return dialog_annotations.get(name) not in {None, "readonly"}


def _dialog_annotation_map(dialog_tools_py: Path) -> dict[str, str]:
    text = dialog_tools_py.read_text(encoding="utf-8")
    mapping: dict[str, str] = {}
    pattern = re.compile(
        r"mcp\.tool\(annotations=(READONLY|ADDITIVE|CONFIRMED_WRITE)\)\(tool_error_handler\((\w+)\)\)"
    )
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
        if _is_unexpected_default_surface_tool(name, dialog_annotations)
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
            or _is_unexpected_default_surface_tool(tool, dialog_annotations)
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
    recovery_sessions = sorted(str(path) for path in MIRROR_ROOT.glob("data/*.session*"))
    runtime_sessions = sorted(str(path) for path in MIRROR_RUNTIME_ROOT.glob("data/*.session*"))
    ledgers = sorted(str(path) for path in (MIRROR_RUNTIME_ROOT / "data/telegram_sync").glob("*.json"))
    runtime_exports = MIRROR_RUNTIME_ROOT / "runtime/ingest/telegram/exports"
    export_coverage = _mirror_export_coverage(runtime_exports)
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
    if recovery_sessions:
        findings.append(
            {
                "id": "mirror_runtime_sessions_in_tree",
                "severity": "warn" if recovery_mode else "blocking",
                "message": "Session files exist inside telegram-mirror recovery tree.",
                "count": len(recovery_sessions),
            }
        )
    if not MIRROR_RUNTIME_ROOT.exists():
        findings.append(
            {
                "id": "mirror_runtime_root_missing",
                "severity": "warn" if recovery_mode else "blocking",
                "message": "External telegram-mirror runtime root is missing.",
            }
        )
    if not runtime_exports.exists():
        findings.append(
            {
                "id": "mirror_runtime_exports_missing",
                "severity": "warn" if recovery_mode else "blocking",
                "message": "Canonical mirror runtime export root is missing.",
                "expected_exports": export_coverage.get("expected_count"),
            }
        )
    elif export_coverage.get("missing_count"):
        findings.append(
            {
                "id": "mirror_runtime_exports_incomplete",
                "severity": "warn" if recovery_mode else "blocking",
                "message": "Canonical mirror runtime export root is missing expected channel exports.",
                "expected_exports": export_coverage.get("expected_count"),
                "ready_exports": export_coverage.get("ready_count"),
                "missing_exports": export_coverage.get("missing_count"),
            }
        )
    return {
        "status": status_from_findings(findings),
        "classification": mirror_policy.get("classification") or "mirror-recovery",
        "findings": findings,
        "policy": mirror_policy,
        "root": str(MIRROR_ROOT),
        "runtime_root": str(MIRROR_RUNTIME_ROOT),
        "legacy_alias": {
            "path": str(MIRROR_LEGACY_ALIAS),
            "exists": legacy_alias_exists,
            "resolved": str(MIRROR_LEGACY_ALIAS.resolve()) if legacy_alias_exists else None,
        },
        "recovery_docs": {name: {"path": str(path), "exists": path.exists()} for name, path in recovery_docs.items()},
        "runtime_state": {
            "recovery_sessions": recovery_sessions,
            "sessions": runtime_sessions,
            "ledgers": ledgers,
            "runtime_root_exists": MIRROR_RUNTIME_ROOT.exists(),
            "runtime_exports_exists": runtime_exports.exists(),
            "export_coverage": export_coverage,
        },
    }


def _mirror_export_coverage(export_root: Path) -> dict[str, Any]:
    allowlist_report = run_json(
        ["python3", str(MIRROR_ROOT / "scripts/telegram_mirror_allowlist_report.py"), "--json"],
        timeout=30,
    )
    channels = allowlist_report.get("channels") if isinstance(allowlist_report.get("channels"), list) else []
    expected = []
    for channel in channels:
        if not isinstance(channel, dict) or not channel.get("retained"):
            continue
        folder = str(channel.get("export_folder") or "").strip()
        if folder:
            expected.append({"name": channel.get("name"), "export_folder": folder})
    ready = [item for item in expected if (export_root / item["export_folder"] / "messages_raw.jsonl").exists()]
    missing = [item for item in expected if item not in ready]
    return {
        "source": "allowlist_report",
        "export_root": str(export_root),
        "expected_count": len(expected),
        "ready_count": len(ready),
        "missing_count": len(missing),
        "missing": missing,
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
    runtime_exports = MIRROR_RUNTIME_ROOT / "runtime/ingest/telegram/exports"
    venv_python = MIRROR_ROOT / ".venv/bin/python"
    ledgers = mirror.get("runtime_state", {}).get("ledgers")
    recovery_sessions = mirror.get("runtime_state", {}).get("recovery_sessions")
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
            "status": "ok" if not recovery_sessions else "fail",
            "message": "Runtime sessions must be owned outside the recovery source tree before promotion.",
            "evidence": {
                "session_count_in_tree": len(recovery_sessions) if isinstance(recovery_sessions, list) else None
            },
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


def _telecrawl_manifest_path(db_path: Path | None = None) -> Path:
    db_path = db_path or TELECRAWL_DEFAULT_DB
    return db_path.with_name(f"{db_path.name}.manifest.json")


def _telecrawl_non_retryable_error_types(policy: dict[str, Any] | None = None) -> set[str]:
    configured = policy.get("non_retryable_error_types") if isinstance(policy, dict) else None
    if not isinstance(configured, list):
        return set(DEFAULT_NON_RETRYABLE_TELECRAWL_ERRORS)
    return {item for item in configured if isinstance(item, str) and item}


def _telecrawl_import_gaps(
    db_path: Path | None = None,
    *,
    non_retryable_error_types: set[str] | None = None,
) -> dict[str, Any]:
    db_path = db_path or TELECRAWL_DEFAULT_DB
    non_retryable_error_types = non_retryable_error_types or set(DEFAULT_NON_RETRYABLE_TELECRAWL_ERRORS)
    if not db_path.exists():
        return {
            "has_known_gaps": False,
            "has_retryable_gaps": False,
            "has_terminal_gaps": False,
            "errors": 0,
            "retryable_errors": 0,
            "terminal_errors": 0,
            "error_chats": 0,
            "error_summary": [],
            "retryable_error_summary": [],
            "terminal_error_summary": [],
            "non_retryable_error_types": sorted(non_retryable_error_types),
        }
    try:
        with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
            tables = {
                row[0]
                for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            }
            if "import_errors" not in tables:
                return {
                    "has_known_gaps": False,
                    "has_retryable_gaps": False,
                    "has_terminal_gaps": False,
                    "errors": 0,
                    "retryable_errors": 0,
                    "terminal_errors": 0,
                    "error_chats": 0,
                    "error_summary": [],
                    "retryable_error_summary": [],
                    "terminal_error_summary": [],
                    "non_retryable_error_types": sorted(non_retryable_error_types),
                }
            summary = [
                {"error_type": row[0], "chats": int(row[1] or 0), "attempts": int(row[2] or 0)}
                for row in conn.execute(
                    "SELECT error_type, COUNT(DISTINCT chat_jid) AS chats, COUNT(*) AS attempts "
                    "FROM import_errors GROUP BY error_type ORDER BY attempts DESC"
                ).fetchall()
            ]
            retryable_summary = [row for row in summary if row["error_type"] not in non_retryable_error_types]
            terminal_summary = [row for row in summary if row["error_type"] in non_retryable_error_types]
            row = conn.execute(
                "SELECT COUNT(*) AS errors, COUNT(DISTINCT chat_jid) AS error_chats FROM import_errors"
            ).fetchone()
    except sqlite3.Error as exc:
        return {
            "has_known_gaps": True,
            "has_retryable_gaps": True,
            "has_terminal_gaps": False,
            "errors": None,
            "retryable_errors": None,
            "terminal_errors": None,
            "error_chats": None,
            "error_summary": [{"error_type": "sqlite_error", "chats": None, "attempts": None}],
            "retryable_error_summary": [{"error_type": "sqlite_error", "chats": None, "attempts": None}],
            "terminal_error_summary": [],
            "non_retryable_error_types": sorted(non_retryable_error_types),
            "read_error": str(exc),
        }
    total_errors = int(row[0] or 0) if row else 0
    terminal_errors = sum(int(item["attempts"] or 0) for item in terminal_summary)
    retryable_errors = total_errors - terminal_errors
    return {
        "has_known_gaps": bool(total_errors),
        "has_retryable_gaps": retryable_errors > 0,
        "has_terminal_gaps": terminal_errors > 0,
        "errors": total_errors,
        "retryable_errors": retryable_errors,
        "terminal_errors": terminal_errors,
        "error_chats": int(row[1] or 0) if row else 0,
        "error_summary": summary,
        "retryable_error_summary": retryable_summary,
        "terminal_error_summary": terminal_summary,
        "non_retryable_error_types": sorted(non_retryable_error_types),
        "retry_policy": {
            "retry_only_when_has_retryable_gaps": True,
            "do_not_retry_terminal_gaps": True,
        },
    }


def _telecrawl_default_archive_status(
    db_path: Path | None = None,
    *,
    non_retryable_error_types: set[str] | None = None,
) -> dict[str, Any]:
    db_path = db_path or TELECRAWL_DEFAULT_DB
    manifest = load_json(_telecrawl_manifest_path(db_path)) or {}
    import_state = manifest.get("import") if isinstance(manifest.get("import"), dict) else {}
    counts = manifest.get("counts") if isinstance(manifest.get("counts"), dict) else {}
    gaps = _telecrawl_import_gaps(db_path, non_retryable_error_types=non_retryable_error_types)
    manifest_status = manifest.get("manifest_status")
    coverage_claim = manifest.get("coverage_claim", "unknown_archive_snapshot")
    if gaps.get("has_known_gaps"):
        coverage_claim = "partial_archive_snapshot_with_known_gaps"
    return {
        "ok": True,
        "source": "telecrawl",
        "source_kind": manifest.get("source_kind", "archive_snapshot"),
        "read_strategy": "manifest_plus_import_errors",
        "coverage_claim": coverage_claim,
        "manifest_coverage_claim": manifest.get("coverage_claim"),
        "manifest_status": manifest_status,
        "archive_ready": db_path.exists() and manifest_status == "complete",
        "import_gaps": gaps,
        "last_complete_import_at": import_state.get("last_complete_import_at"),
        "status": {
            "chats": counts.get("chats"),
            "messages": counts.get("messages"),
            "media_messages": counts.get("media_messages"),
            "oldest_message": counts.get("oldest_message"),
            "newest_message": counts.get("newest_message"),
        },
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }


def audit_telecrawl() -> dict[str, Any]:
    telecrawl_policy = load_json(POLICY_DIR / "telecrawl.json") or {}
    non_retryable_error_types = _telecrawl_non_retryable_error_types(telecrawl_policy)
    accounts = _safe_read_telecrawl_json(["accounts"], timeout=30)
    status = _telecrawl_default_archive_status(non_retryable_error_types=non_retryable_error_types)
    findings: list[dict[str, Any]] = []
    account_rows = accounts.get("accounts") if isinstance(accounts.get("accounts"), list) else []
    active_incomplete = [
        row
        for row in account_rows
        if row.get("active") and (not row.get("db_exists") or row.get("manifest_stale_or_missing"))
    ]
    if active_incomplete:
        findings.append(
            {
                "id": "telecrawl_active_archives_incomplete",
                "severity": "warn",
                "message": "Telecrawl account catalog contains active accounts with missing or stale archives.",
                "count": len(active_incomplete),
            }
        )
    import_gaps = status.get("import_gaps") if isinstance(status.get("import_gaps"), dict) else {}
    if import_gaps.get("has_known_gaps"):
        severity = (
            "warn"
            if telecrawl_policy.get("known_gaps_are_blocking_for_archive_search") is False
            else "blocking"
        )
        retryable = import_gaps.get("retryable_error_summary")
        terminal = import_gaps.get("terminal_error_summary")
        retryable_count = len(retryable) if isinstance(retryable, list) else 0
        terminal_count = len(terminal) if isinstance(terminal, list) else 0
        expected_ids = telecrawl_policy.get("expected_doctor_warning_ids")
        expected_gap_warning = (
            isinstance(expected_ids, list)
            and "telecrawl_known_gaps" in expected_ids
            and severity == "warn"
        )
        findings.append(
            {
                "id": "telecrawl_known_gaps",
                "severity": severity,
                "message": (
                    "Telecrawl default archive has known import gaps "
                    f"({retryable_count} retryable, {terminal_count} terminal); "
                    "not a control-plane release blocker."
                    if expected_gap_warning
                    else "Telecrawl default archive has known import gaps."
                ),
                "summary": import_gaps.get("error_summary"),
                "retryable_summary": retryable,
                "terminal_summary": terminal,
                "retry_policy": import_gaps.get("retry_policy"),
                "expected_operational_warning": expected_gap_warning,
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
        "docs": audit_docs(),
        "plugin_drift": audit_plugin_drift(),
        "mcp_telemetry": audit_mcp_telemetry(),
        "fast_read_adapter": audit_fast_read_adapter(),
        "agent_docs_sync": audit_agent_docs_sync(),
        "release_gates": audit_release_gates(),
        "install_adapters": audit_install_adapters(),
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
    if name == "mcp_telemetry":
        summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
        tool_latency = summary.get("tool_latency") if isinstance(summary.get("tool_latency"), dict) else {}
        return {
            "status": report.get("status"),
            "findings": report.get("findings", []),
            "events_in_window": report.get("events_in_window"),
            "tool_errors": report.get("tool_errors"),
            "cache_hit_rate": report.get("cache_hit_rate"),
            "stats_file_present": report.get("stats_file_present"),
            "tools_observed": sorted(tool_latency.keys())[:8],
        }
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
        recovery_sessions = (
            runtime_state.get("recovery_sessions") if isinstance(runtime_state.get("recovery_sessions"), list) else []
        )
        ledgers = runtime_state.get("ledgers") if isinstance(runtime_state.get("ledgers"), list) else []
        export_coverage = (
            runtime_state.get("export_coverage") if isinstance(runtime_state.get("export_coverage"), dict) else {}
        )
        return {
            **report,
            "runtime_state_summary": {
                "session_count": len(sessions),
                "recovery_session_count": len(recovery_sessions),
                "ledger_count": len(ledgers),
                "runtime_root_exists": bool(runtime_state.get("runtime_root_exists")),
                "runtime_exports_exists": bool(runtime_state.get("runtime_exports_exists")),
                "export_expected_count": export_coverage.get("expected_count"),
                "export_ready_count": export_coverage.get("ready_count"),
                "export_missing_count": export_coverage.get("missing_count"),
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
