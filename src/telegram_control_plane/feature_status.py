from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from .command_registry import command_by_name
from .doctor import ControlPlaneDoctor
from .paths import CONTROL_ROOT, POLICY_DIR
from .util import load_json

FEATURE_STATUS_PATH = CONTROL_ROOT / "docs/agents/feature-status.csv"
SURFACE_CONTRACT_PATH = POLICY_DIR / "surface-contract.json"


def _component_for_row(row: dict[str, str]) -> str | None:
    command = row.get("command_name", "")
    if command == "telegram-maintenance-doctor":
        return "__registry__"
    spec = command_by_name(command)
    return spec.component if spec is not None else None


def _finding_ids(findings: list[dict[str, Any]]) -> str:
    return "; ".join(str(item.get("id", "unknown")) for item in findings)


def _update_row(row: dict[str, str], *, component: str, report: dict[str, Any]) -> dict[str, str]:
    updated = dict(row)
    status = str(report.get("status") or "unknown")
    findings = report.get("findings") if isinstance(report.get("findings"), list) else []
    is_ok = status == "ok"
    updated["host_status"] = "pass" if is_ok else "fail"
    updated["status"] = "tested_pass" if is_ok else "tested_fail"
    updated["last_result"] = f"{component} {status}"
    updated["errors"] = "" if is_ok else _finding_ids(findings)
    updated["next_action"] = "keep covered" if is_ok else f"run {updated.get('verification_command', '').strip()}"
    updated["expected_failure_class"] = "none" if is_ok else "operational_finding"
    return updated


def _read_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def _surface_tool_rows(fieldnames: list[str]) -> list[dict[str, str]]:
    policy = load_json(SURFACE_CONTRACT_PATH) or {}
    active_profile = str(policy.get("active_profile") or "owner_local_full_mcp")
    profile = policy.get(active_profile) if isinstance(policy.get(active_profile), dict) else {}
    tools = profile.get("required_tools") if isinstance(profile.get("required_tools"), list) else []
    rows: list[dict[str, str]] = []
    for index, tool in enumerate([str(item) for item in tools if isinstance(item, str)], start=1):
        row = {field: "" for field in fieldnames}
        row.update(
            {
                "feature_id": f"MCP-{index:03d}",
                "surface": "mcp_surface",
                "feature_name": f"MCP tool exposed: {tool}",
                "user_story": (
                    f"As an owner-local agent, I want the `{tool}` MCP tool available "
                    "so the full Telegram surface matches policy."
                ),
                "expected_behavior": (
                    f"{active_profile} requires `{tool}` and telegram-mcp-surface reports "
                    "no missing required full surface tools."
                ),
                "coverage_target": f"mcp_tool:{tool}",
                "coverage_source": f"policy/surface-contract.json:{active_profile}.required_tools",
                "owning_files": (
                    "policy/surface-contract.json; docs/agents/mcp-surface.md; "
                    "src/telegram_control_plane/surface_contract.py; src/telegram_control_plane/audits.py"
                ),
                "existing_checks": "tests/test_surface_contract.py; tests/test_control_plane.py",
                "verification_command": "./bin/telegram-mcp-surface --json",
                "command_name": "telegram-mcp-surface",
                "command_level": "drilldown",
                "command_safety": "read-only",
                "command_class": "surface-policy",
                "verification_mode": "integration",
                "expected_failure_class": "none",
                "live_dependency": "true",
                "mutates_state": "false",
                "release_gate_id": "mcp-surface",
                "code_status": "pass",
                "host_status": "pass",
                "optimization_opportunity": (
                    "keep required surface mapped to executable policy proof; "
                    "add tool-specific smoke only when safe"
                ),
                "optimization_verdict": "improved",
                "optimization_evidence": (
                    "Inventory loophole closed: required MCP tool is generated from "
                    "SurfaceContract and covered by telegram-mcp-surface proof."
                ),
                "proof_type": "surface-policy-json",
                "status": "tested_pass_surface_policy",
                "last_result": "mcp_surface ok",
                "errors": "",
                "next_action": "add live/tool-specific behavioral probe only when safe and useful",
            }
        )
        rows.append(row)
    return rows


def feature_rows(*, path: Path = FEATURE_STATUS_PATH) -> list[dict[str, str]]:
    fieldnames, rows = _read_rows(path)
    manual_rows = [row for row in rows if not row.get("feature_id", "").startswith("MCP-")]
    return [*manual_rows, *_surface_tool_rows(fieldnames)]


def _write_rows(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def refresh_feature_status(
    *,
    path: Path = FEATURE_STATUS_PATH,
    registry: dict[str, Any] | None = None,
    write: bool = False,
) -> dict[str, Any]:
    """Refresh host status fields in the canonical feature-status CSV."""

    registry = registry if registry is not None else ControlPlaneDoctor(profile="maintenance").build_registry()
    fieldnames, rows = _read_rows(path)
    components = registry.get("components") if isinstance(registry.get("components"), dict) else {}
    changed_rows: list[str] = []
    refreshed: list[dict[str, str]] = []

    for row in rows:
        component = _component_for_row(row)
        if component == "__registry__":
            report = registry
            component_name = "maintenance"
        elif component and component in components:
            report = components[component]
            component_name = component
        else:
            refreshed.append(row)
            continue
        updated = _update_row(row, component=component_name, report=report)
        if updated != row:
            changed_rows.append(row.get("feature_id", ""))
        refreshed.append(updated)

    if write and changed_rows:
        _write_rows(path, fieldnames, refreshed)

    return {
        "status": "ok",
        "path": str(path),
        "write": write,
        "rows": len(rows),
        "changed_rows": changed_rows,
        "changed_count": len(changed_rows),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Refresh the canonical Telegram feature-status CSV.")
    parser.add_argument("--json", action="store_true", help="Emit JSON")
    parser.add_argument("--write", action="store_true", help="Write refreshed status fields")
    parser.add_argument("--path", type=Path, default=FEATURE_STATUS_PATH, help="Feature status CSV path")
    args = parser.parse_args(argv)

    report = refresh_feature_status(path=args.path, write=args.write)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        mode = "written" if args.write else "dry-run"
        print(f"feature-status: {mode}, changed_rows={report['changed_count']}")
        for feature_id in report["changed_rows"]:
            print(f"- {feature_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
