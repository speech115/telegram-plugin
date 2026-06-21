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
)
from .doctor import ControlPlaneDoctor
from .insights import build_insights
from .paths import OBSERVED_REGISTRY
from .audit_remediation import apply_repair_plan, build_repair_plan
from .api_gap_audit import audit_api_gaps
from .doctor_profiles import PROFILE_COMPONENTS
from .command_registry import registry_report
from .next_actions import build_next_actions, render_next_actions
from .runtime_inventory import audit_runtime_inventory
from .source_routing import audit_source_routing, recommend_route


COMMANDS: dict[str, Callable[[], dict[str, Any]]] = {
    "managed-systems": audit_managed_systems,
    "plugin-drift": audit_plugin_drift,
    "telemetry-status": audit_mcp_telemetry,
    "insights": build_insights,
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
    "source-routing": audit_source_routing,
    "runtime-inventory": audit_runtime_inventory,
    "api-gap-audit": audit_api_gaps,
    "repair-plan": build_repair_plan,
    "repair-plan-apply": apply_repair_plan,
}


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read-only Telegram control-plane")
    parser.add_argument(
        "command",
        choices=["doctor", "status", "route", "commands", "next", *COMMANDS],
        help="Audit command",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON")
    parser.add_argument(
        "--no-write-registry",
        action="store_true",
        help="Do not write generated/observed-registry.json for doctor/status",
    )
    parser.add_argument(
        "--profile",
        choices=sorted(PROFILE_COMPONENTS),
        default="core",
        help="Doctor/status component profile (default: core)",
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
    for item in report.get("recommendations", [])[:20]:
        lines.append(f"- [{item.get('kind')}] {item.get('subject')}: {item.get('recommendation')}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    raw_argv = argv if argv is not None else sys.argv[1:]
    if raw_argv and raw_argv[0] == "route":
        emit_json = "--json" in raw_argv
        intent_tokens = [token for token in raw_argv[1:] if token != "--json"]
        report = recommend_route(" ".join(intent_tokens))
        if emit_json:
            print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            print(f"primary_source: {report.get('primary_source')}")
            print(f"backend: {report.get('backend')}")
            for warning in report.get("warnings", []):
                print(f"warning: {warning}")
        return 0

    args = parse_args(raw_argv)
    if args.command == "commands":
        report = registry_report()
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            for entry in report["commands"]:
                print(
                    f"{entry['name']:<32} {entry['level']:<12} {entry['safety']:<10} "
                    f"{entry['purpose']}"
                )
        return 0
    if args.command == "next":
        doctor = ControlPlaneDoctor(profile=args.profile)
        report = build_next_actions(doctor.build_registry())
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            print(render_next_actions(report))
        return 1 if report.get("status") == "fail" else 0
    if args.command in {"doctor", "status"}:
        doctor = ControlPlaneDoctor(profile=args.profile)
        report = doctor.build_registry()
        if not args.no_write_registry:
            doctor.write_registry(OBSERVED_REGISTRY, report)
    else:
        report = COMMANDS[args.command]()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(render_text(report))
    return 1 if report.get("status") == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
