from __future__ import annotations

import argparse
import json
from typing import Any

from .doctor import ControlPlaneDoctor
from .feature_status import refresh_feature_status
from .runtime_compat import audit_runtime_compat


def _status_icon(status: str) -> str:
    return "ok" if status == "ok" else "check"


def _component_status(registry: dict[str, Any], component: str) -> str:
    components = registry.get("components")
    if not isinstance(components, dict):
        return "unknown"
    report = components.get(component)
    if not isinstance(report, dict):
        return "unknown"
    return str(report.get("status") or "unknown")


def _summary_counts(registry: dict[str, Any]) -> tuple[int, int]:
    summary = registry.get("summary")
    if not isinstance(summary, dict):
        return 0, 0
    return int(summary.get("blocking_findings") or 0), int(summary.get("warning_findings") or 0)


def build_operator_status(*, registry: dict[str, Any] | None = None) -> dict[str, Any]:
    registry = registry if registry is not None else ControlPlaneDoctor(profile="maintenance").build_registry()
    blockers, warnings = _summary_counts(registry)
    feature_status = refresh_feature_status(registry=registry, write=False)
    runtime_compat = audit_runtime_compat()

    checks = [
        {
            "id": "live_telegram",
            "label": "Live Telegram",
            "status": _component_status(registry, "mcp_surface"),
            "evidence": "mcp_surface",
        },
        {
            "id": "telemetry",
            "label": "Telemetry",
            "status": _component_status(registry, "mcp_telemetry"),
            "evidence": "mcp_telemetry",
        },
        {
            "id": "runtime_compat",
            "label": "Runtime schema compat",
            "status": str(runtime_compat.get("status") or "unknown"),
            "evidence": "telegram-runtime-compat",
        },
        {
            "id": "docs",
            "label": "Docs sync",
            "status": _component_status(registry, "agent_docs_sync"),
            "evidence": "agent_docs_sync",
        },
        {
            "id": "feature_status",
            "label": "Feature spreadsheet",
            "status": "ok" if feature_status.get("changed_count") == 0 else "stale",
            "evidence": f"changed_count={feature_status.get('changed_count')}",
        },
        {
            "id": "maintenance",
            "label": "Maintenance doctor",
            "status": str(registry.get("status") or "unknown"),
            "evidence": f"blockers={blockers} warnings={warnings}",
        },
    ]
    status = "ok" if all(item["status"] == "ok" for item in checks) else "warn"
    next_action = "No action needed." if status == "ok" else "Run ./bin/telegram-maintenance-doctor --json --no-write-registry"
    return {
        "status": status,
        "checks": checks,
        "summary": {
            "blocking_findings": blockers,
            "warning_findings": warnings,
            "feature_status_changed_count": feature_status.get("changed_count"),
        },
        "next_action": next_action,
    }


def render_operator_status(report: dict[str, Any]) -> str:
    lines = [f"Telegram operator status: {report.get('status')}"]
    for item in report.get("checks", []):
        if not isinstance(item, dict):
            continue
        status = str(item.get("status") or "unknown")
        lines.append(f"- {_status_icon(status)} {item.get('label')}: {status} ({item.get('evidence')})")
    lines.append(f"Next: {report.get('next_action')}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Human-readable Telegram operator status.")
    parser.add_argument("--json", action="store_true", help="Emit JSON")
    args = parser.parse_args(argv)

    report = build_operator_status()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(render_operator_status(report))
    return 0 if report.get("status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
