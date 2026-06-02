from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Callable

from .audits import (
    audit_docs,
    audit_launchd,
    audit_fast_read_adapter,
    audit_install_adapters,
    audit_managed_systems,
    audit_release_gates,
    audit_mcp_profiles,
    audit_mcp_surface,
    audit_mirror,
    audit_mirror_preflight,
    audit_mcp_telemetry,
    audit_plugin_drift,
    audit_sessions,
    audit_telecrawl,
    build_registry,
    write_registry,
)
from .paths import OBSERVED_REGISTRY
from .planner import apply_repair_plan, build_repair_plan


COMMANDS: dict[str, Callable[[], dict[str, Any]]] = {
    "managed-systems": audit_managed_systems,
    "plugin-drift": audit_plugin_drift,
    "telemetry-status": audit_mcp_telemetry,
    "docs-audit": audit_docs,
    "fast-read-adapter": audit_fast_read_adapter,
    "release-gates": audit_release_gates,
    "install-adapters": audit_install_adapters,
    "mcp-surface": audit_mcp_surface,
    "mcp-profiles": audit_mcp_profiles,
    "launchd-audit": audit_launchd,
    "session-audit": audit_sessions,
    "mirror-audit": audit_mirror,
    "mirror-preflight": audit_mirror_preflight,
    "telecrawl-status": audit_telecrawl,
    "repair-plan": build_repair_plan,
    "repair-plan-apply": apply_repair_plan,
}


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read-only Telegram control-plane")
    parser.add_argument("command", choices=["doctor", "status", *COMMANDS], help="Audit command")
    parser.add_argument("--json", action="store_true", help="Emit JSON")
    parser.add_argument(
        "--no-write-registry",
        action="store_true",
        help="Do not write generated/observed-registry.json for doctor/status",
    )
    return parser.parse_args(argv)


def render_text(report: dict[str, Any]) -> str:
    lines = [f"status: {report.get('status')}"]
    summary = report.get("summary")
    if isinstance(summary, dict):
        lines.append(f"blocking_findings: {summary.get('blocking_findings')}")
        lines.append(f"warning_findings: {summary.get('warning_findings')}")
        components = summary.get("components")
        if isinstance(components, dict):
            for name, status in components.items():
                lines.append(f"{name}: {status}")
    for item in report.get("findings", [])[:20]:
        lines.append(f"- [{item.get('severity')}] {item.get('component', '?')}/{item.get('id')}: {item.get('message')}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    if args.command in {"doctor", "status"}:
        report = build_registry()
        if not args.no_write_registry:
            write_registry(OBSERVED_REGISTRY, report)
    else:
        report = COMMANDS[args.command]()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(render_text(report))
    return 1 if report.get("status") == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
