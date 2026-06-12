from __future__ import annotations

import ast
import copy
import os
import plistlib
import re
import sqlite3
import subprocess
from pathlib import Path
from typing import Any

from .paths import (
    CONTROL_ROOT,
    FAST_READ_ADAPTER,
    HOME,
    TG_CLI,
    LAUNCHAGENTS_DIR,
    LIVE_SKILL,
    MCP_REPO,
    MCP_TELEMETRY_DIR,
    MCP_TELEMETRY_LOG,
    MCP_TELEMETRY_STATS,
    TELEMETRY_ALERT_THRESHOLDS,
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
from . import managed_systems, surface_contract, telecrawl_gap
from .surface_contract import WRITE_OR_DESTRUCTIVE_RE
from .util import load_json, run_json, status_from_findings

APPROVED_FACADE_TOOLS = surface_contract.approved_facade_tools()
PATH_LIKE_RE = re.compile(
    rf"^({re.escape(str(HOME / 'Projects'))}|{re.escape(str(HOME))}/\.|/tmp|/private/tmp|/opt|/usr/local|/bin|/usr/bin)"
)

SECRET_ENV_KEYS = {"TELEGRAM_API_HASH", "TELEGRAM_SESSION_STRING"}


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


def _telemetry_thresholds() -> dict[str, Any]:
    payload = load_json(TELEMETRY_ALERT_THRESHOLDS) or {}
    return payload if isinstance(payload, dict) else {}


def _prometheus_target_status(port: int, *, timeout: float = 2.0) -> dict[str, Any]:
    import urllib.error
    import urllib.request

    url = f"http://127.0.0.1:{port}/metrics"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            body = response.read(512).decode("utf-8", errors="replace")
            return {
                "port": port,
                "status": "ok" if response.status == 200 else "fail",
                "http_status": response.status,
                "sample": body.splitlines()[:3],
            }
    except urllib.error.URLError as exc:
        return {"port": port, "status": "down", "error": str(exc)}


def audit_mcp_telemetry(*, window_hours: float | None = None) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    python_bin = MCP_REPO / ".venv/bin/python"
    thresholds = _telemetry_thresholds()
    effective_window = float(window_hours if window_hours is not None else thresholds.get("window_hours", 24))

    summary: dict[str, Any]
    if python_bin.exists():
        summary = run_json(
            [
                str(python_bin),
                "-m",
                "telegram_mcp.telemetry",
                "--summarize",
                "--json",
                "--log-dir",
                str(MCP_TELEMETRY_DIR),
                "--window-hours",
                str(effective_window),
            ],
            timeout=60,
        )
    else:
        summary = {
            "status": "missing",
            "log_path": str(MCP_TELEMETRY_DIR),
            "events_in_window": 0,
        }

    summary_status = summary.get("status")
    events_in_window = int(summary.get("events_in_window") or 0)
    tool_errors = int(summary.get("tool_errors") or 0)
    min_events = int(thresholds.get("min_events_for_rate_checks", 20))
    max_tool_errors = int(thresholds.get("max_tool_errors", 10))
    max_error_rate = float(thresholds.get("max_tool_error_rate", 0.25))
    max_read_p95 = float(thresholds.get("max_telegram_read_p95_ms", 5000))

    if summary_status == "missing":
        findings.append(
            {
                "id": "telemetry_log_missing",
                "severity": "warn",
                "message": (
                    "MCP telemetry logs are not present yet. Restart HTTP MCP with "
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
                    f"No telemetry events in the last {effective_window:g}h. "
                    "Confirm MCP HTTP daemons are running and receiving tool traffic."
                ),
            }
        )
    elif tool_errors >= max_tool_errors:
        findings.append(
            {
                "id": "telemetry_high_tool_error_count",
                "severity": "warn",
                "message": f"MCP telemetry recorded {tool_errors} tool errors in the recent window.",
            }
        )

    tool_calls = int(summary.get("event_counts", {}).get("tool_call", 0)) if isinstance(summary.get("event_counts"), dict) else 0
    if tool_calls >= min_events and tool_errors / tool_calls > max_error_rate:
        findings.append(
            {
                "id": "telemetry_high_tool_error_rate",
                "severity": "warn",
                "message": (
                    f"Tool error rate {tool_errors}/{tool_calls} exceeds "
                    f"{max_error_rate:.0%} in the telemetry window."
                ),
            }
        )

    tool_latency = summary.get("tool_latency") if isinstance(summary.get("tool_latency"), dict) else {}
    read_stats = tool_latency.get("telegram_read") if isinstance(tool_latency.get("telegram_read"), dict) else {}
    read_p95 = read_stats.get("p95_ms")
    if isinstance(read_p95, int | float) and read_p95 > max_read_p95:
        findings.append(
            {
                "id": "telemetry_slow_telegram_read",
                "severity": "warn",
                "message": f"telegram_read p95 {read_p95}ms exceeds {max_read_p95:g}ms threshold.",
            }
        )

    agent_preflight = summary.get("agent_preflight") if isinstance(summary.get("agent_preflight"), dict) else {}
    preflight_violations = agent_preflight.get("preflight_violations")
    max_preflight = thresholds.get("max_preflight_violations")
    if (
        isinstance(preflight_violations, int)
        and isinstance(max_preflight, int)
        and preflight_violations > max_preflight
    ):
        findings.append(
            {
                "id": "telemetry_preflight_violations",
                "severity": "warn",
                "message": (
                    f"Recorded {preflight_violations} preflight violations "
                    f"(doctor/get_me before first read); threshold is {max_preflight}."
                ),
            }
        )

    prometheus_ports = thresholds.get("prometheus_metrics_ports")
    metrics_targets: list[dict[str, Any]] = []
    if isinstance(prometheus_ports, list):
        for raw_port in prometheus_ports:
            if isinstance(raw_port, int):
                metrics_targets.append(_prometheus_target_status(raw_port))
    metrics_up = [item for item in metrics_targets if item.get("status") == "ok"]
    if isinstance(prometheus_ports, list) and prometheus_ports and not metrics_up:
        findings.append(
            {
                "id": "telemetry_prometheus_down",
                "severity": "warn",
                "message": (
                    "No Telegram MCP Prometheus /metrics targets responded. "
                    "Set TELEGRAM_TELEMETRY_METRICS_PORT per LaunchAgent (e.g. 9109, 9110) and restart MCP."
                ),
            }
        )

    cache = summary.get("cache") if isinstance(summary.get("cache"), dict) else {}
    source_counts = summary.get("source_counts") if isinstance(summary.get("source_counts"), dict) else {}
    return {
        "status": status_from_findings(findings),
        "findings": findings,
        "summary": summary,
        "artifacts": {
            "telemetry_log": str(MCP_TELEMETRY_LOG),
            "telemetry_log_dir": str(MCP_TELEMETRY_DIR),
            "telemetry_stats": str(MCP_TELEMETRY_STATS),
            "prometheus_scrape": str(CONTROL_ROOT / "policy/telemetry/prometheus-scrape.yml"),
            "prometheus_alerts": str(CONTROL_ROOT / "policy/telemetry/prometheus-alerts.yml"),
            "grafana_dashboard": str(CONTROL_ROOT / "policy/telemetry/grafana-dashboard.json"),
        },
        "stats_file_present": MCP_TELEMETRY_STATS.exists(),
        "events_in_window": events_in_window,
        "tool_errors": tool_errors,
        "cache_hit_rate": cache.get("hit_rate"),
        "source_counts": source_counts,
        "prometheus_targets": metrics_targets,
    }


DOC_AUDIT_PATHS = (
    CONTROL_ROOT / "AGENTS.md",
    CONTROL_ROOT / "README.md",
    CONTROL_ROOT / "PLAN.md",
)
DOC_PLUGIN_VERSION_RE = re.compile(r"plugin version `(\d+\.\d+\.\d+)`")


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
        findings.extend(
            surface_contract.evaluate_docs_surface_contract(
                doc_name=path.name,
                text=text,
            )
        )

    return {
        "status": status_from_findings(findings),
        "findings": findings,
        "checked_paths": checked,
        "plugin_version": plugin_version,
        "surface_contract": surface_contract.contract_summary(),
        "deprecated_default_surface_tools": sorted(surface_contract.deprecated_doc_tools()),
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


def audit_golden_read_smoke(*, probe_only: bool = True) -> dict[str, Any]:
    """Live read smoke against golden dialogs (probe=me only by default)."""

    from .golden_read_smoke import run_golden_read_smoke

    dialog_ids = ["saved-messages"] if probe_only else None
    raw = run_golden_read_smoke(limit=1, timeout=25.0, dialog_ids=dialog_ids)
    findings: list[dict[str, Any]] = []
    if raw.get("status") != "ok":
        for item in raw.get("findings", []):
            if not isinstance(item, dict):
                continue
            findings.append(
                {
                    "id": "golden_read_smoke_failed",
                    "severity": "warn" if probe_only else "blocking",
                    "message": str(item.get("message") or "golden read smoke failed"),
                    "dialog": item.get("dialog"),
                }
            )
        if not findings:
            findings.append(
                {
                    "id": "golden_read_smoke_failed",
                    "severity": "warn" if probe_only else "blocking",
                    "message": "Golden read smoke failed without details.",
                }
            )

    return {
        "status": status_from_findings(findings),
        "findings": findings,
        "probe_only": probe_only,
        "dialogs": raw.get("dialogs", []),
        "manifest_path": raw.get("manifest_path"),
    }


def audit_fast_read_adapter() -> dict[str, Any]:
    """Verify the local read-only fast path used before mcporter for simple reads."""

    import shutil

    findings: list[dict[str, Any]] = []
    adapters: list[dict[str, Any]] = []
    tg_on_path = shutil.which("tg")
    kit_wrapper = CONTROL_ROOT / "bin" / "tg"
    if not tg_on_path and os.environ.get("TELEGRAM_CI_PORTABLE") != "1":
        findings.append(
            {
                "id": "tg_not_on_path",
                "severity": "warn",
                "message": (
                    "tg is not on PATH; Codex agents may miss the fast read hot path. "
                    "Run: ./bin/telegram-kit --local"
                ),
            }
        )
    elif tg_on_path and kit_wrapper.is_file():
        try:
            path_tg = Path(tg_on_path).resolve()
            kit_tg = kit_wrapper.resolve()
            mcp_tg = Path(TG_CLI).resolve()
        except OSError:
            path_tg = kit_tg = mcp_tg = None
        if (
            path_tg
            and kit_tg
            and mcp_tg
            and path_tg not in {kit_tg, mcp_tg}
            and os.environ.get("TELEGRAM_CI_PORTABLE") != "1"
        ):
            findings.append(
                {
                    "id": "tg_path_shadows_kit",
                    "severity": "warn",
                    "message": (
                        f"PATH tg ({path_tg}) is not the kit wrapper ({kit_tg}) or MCP tg ({mcp_tg}). "
                        "Run: ./bin/telegram-kit --local"
                    ),
                    "path_tg": str(path_tg),
                    "kit_tg": str(kit_tg),
                }
            )

    for label, path, usage_needle in (
        ("tg", TG_CLI, "tg"),
        ("telegram-fast-read-today", FAST_READ_ADAPTER, "telegram-fast-read-today"),
    ):
        exists = path.is_file()
        executable = exists and path.stat().st_mode & 0o111 != 0
        command = [str(path), "--help"]
        help_probe: dict[str, Any] = {"ran": False}
        if not exists:
            findings.append(
                {
                    "id": f"fast_read_adapter_missing_{label}",
                    "severity": "blocking" if label == "tg" else "warn",
                    "message": f"{label} adapter is missing.",
                }
            )
        elif not executable:
            findings.append(
                {
                    "id": f"fast_read_adapter_not_executable_{label}",
                    "severity": "blocking" if label == "tg" else "warn",
                    "message": f"{label} adapter exists but is not executable.",
                }
            )
        else:
            try:
                completed = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    timeout=20,
                    check=False,
                )
            except subprocess.TimeoutExpired:
                completed = subprocess.CompletedProcess(command, 124, "", "help probe timed out")
            help_probe = {
                "ran": True,
                "exit_code": completed.returncode,
                "stdout_contains_usage": usage_needle in completed.stdout,
            }
            if completed.returncode != 0 or usage_needle not in completed.stdout:
                findings.append(
                    {
                        "id": f"fast_read_adapter_help_failed_{label}",
                        "severity": "blocking" if label == "tg" else "warn",
                        "message": f"{label} --help probe failed.",
                    }
                )
        adapters.append(
            {
                "label": label,
                "path": str(path),
                "exists": exists,
                "executable": executable,
                "help_probe": help_probe,
            }
        )

    tg_module = MCP_REPO / "src/telegram_mcp/tg_cli.py"
    tg_source = tg_module.read_text(encoding="utf-8", errors="replace") if tg_module.is_file() else ""
    if '"telegram_read"' not in tg_source:
        findings.append(
            {
                "id": "tg_cli_stale_tool",
                "severity": "blocking",
                "message": "telegram_mcp.tg_cli must call telegram_read on the default MCP surface.",
            }
        )

    legacy_source = FAST_READ_ADAPTER.read_text(encoding="utf-8", errors="replace") if FAST_READ_ADAPTER.is_file() else ""
    if legacy_source and "telegram_mcp.fast_read_today" not in legacy_source:
        findings.append(
            {
                "id": "fast_read_adapter_wrapper_drift",
                "severity": "warn",
                "message": "telegram-fast-read-today must delegate to telegram_mcp.fast_read_today.",
            }
        )

    return {
        "status": status_from_findings(findings),
        "findings": findings,
        "adapter": adapters[0] if adapters else {},
        "adapters": adapters,
        "tg_on_path": tg_on_path,
        "routing": {
            "first_path_for": ["simple_today_read", "simple_recent_read", "dialog_search"],
            "cli": "tg",
            "fallback": "live_mcp_facade",
            "never_for": ["send", "reply", "media_inspection", "subscriber_export"],
            "codex_hot_path_doc": "generated/adapters/codex/telegram-codex-entry.md",
        },
    }


def audit_agent_docs_sync() -> dict[str, Any]:
    """Ensure MCP docs/agent matches plugin references manifest."""

    sync_tool = MCP_REPO / "bin/sync-agent-docs"
    if not sync_tool.exists():
        return {
            "status": "ok",
            "findings": [],
            "command": [str(sync_tool)],
            "skipped": True,
            "reason": "agent docs sync tool is not present in this package layout",
        }

    command = [
        str(sync_tool),
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
        if isinstance(content, str) and str(HOME) in content:
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


def audit_managed_systems() -> dict[str, Any]:
    source_manifest = load_json(PLUGIN_SOURCE / ".codex-plugin/plugin.json") or {}
    source_version = source_manifest.get("version")
    cache_version = PLUGIN_CACHE.name if PLUGIN_CACHE.parent == PLUGIN_CACHE_ROOT else ""
    plugin_source_version = source_version if isinstance(source_version, str) and source_version else None
    plugin_cache_version = cache_version if isinstance(cache_version, str) and cache_version else None
    return managed_systems.evaluate_managed_systems(
        plugin_source_version=plugin_source_version,
        plugin_cache_version=plugin_cache_version,
    )


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
    surface_eval = surface_contract.evaluate_default_surface_tools(
        effective_default_tools,
        dialog_annotations,
    )
    unexpected_write = surface_eval["unexpected_write_or_destructive_tools"]
    non_facade = surface_eval["non_facade_tools"]
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
            if surface_contract.is_unsafe_plugin_allowlist_tool(tool, dialog_annotations)
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
        if allowlist is not None:
            drift = surface_contract.evaluate_plugin_allowlist_contract(set(allowlist))
            if not drift["matches_contract"]:
                findings.append(
                    {
                        "id": "plugin_allowlist_surface_contract_drift",
                        "severity": "blocking",
                        "message": (
                            f"MCP server {name!r} allowlist does not match surface-contract.json."
                        ),
                        "extra_tools": drift["extra_tools"],
                        "missing_tools": drift["missing_tools"],
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
        "surface_contract": surface_contract.contract_summary(),
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
                "session_dir": row.get("telegram_session_dir") or str(HOME / ".telegram-mcp/session"),
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
        HOME / ".telegram-mcp/session.session",
        HOME / ".telegram-mcp-pl/session.session",
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


def audit_mirror_fast_status() -> dict[str, Any]:
    mirror_policy = load_json(POLICY_DIR / "mirror.json") or {}
    runtime_exports = MIRROR_RUNTIME_ROOT / "runtime/ingest/telegram/exports"
    ledgers_root = MIRROR_RUNTIME_ROOT / "data/telegram_sync"
    ledgers = sorted(ledgers_root.glob("*.json")) if ledgers_root.exists() else []
    findings: list[dict[str, Any]] = []
    if not MIRROR_RUNTIME_ROOT.exists():
        findings.append(
            {
                "id": "mirror_runtime_root_missing",
                "severity": "warn",
                "message": "Mirror runtime root is missing.",
            }
        )
    return {
        "status": status_from_findings(findings),
        "findings": findings,
        "classification": mirror_policy.get("classification") or "mirror-recovery",
        "runtime_root_exists": MIRROR_RUNTIME_ROOT.exists(),
        "runtime_exports_exists": runtime_exports.exists(),
        "ledger_count": len(ledgers),
        "fast_command": "telegram-mirror-fast status",
        "maintenance_command": "telegram-mirror-audit",
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


def audit_telecrawl() -> dict[str, Any]:
    telecrawl_policy = telecrawl_gap.load_telecrawl_policy()
    terminal_types = telecrawl_gap.non_retryable_error_types(telecrawl_policy)
    accounts = _safe_read_telecrawl_json(["accounts"], timeout=30)
    status = telecrawl_gap.default_archive_status(
        TELECRAWL_DEFAULT_DB,
        non_retryable_error_types=terminal_types,
    )
    readiness = telecrawl_gap.evaluate_archive_readiness(
        accounts=accounts,
        archive_status=status,
        policy=telecrawl_policy,
    )
    return {
        "status": readiness["status"],
        "findings": readiness["findings"],
        "wrapper": str(TELECRAWL_ARCHIVE),
        "policy": telecrawl_policy,
        "gap_policy": readiness.get("gap_policy"),
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
    from .doctor import ControlPlaneDoctor

    return ControlPlaneDoctor(profile="maintenance").collect_components()


def build_registry() -> dict[str, Any]:
    from .doctor import ControlPlaneDoctor

    return ControlPlaneDoctor(component_collector=_collect_components).build_registry()


def write_registry(path: Path, registry: dict[str, Any]) -> None:
    from .doctor import ControlPlaneDoctor

    ControlPlaneDoctor().write_registry(path, registry)
