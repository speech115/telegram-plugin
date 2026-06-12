"""Turn a doctor report into a prioritized, executable next-actions list.

This is the agent's first call: it answers "what should I do right now"
with exact commands instead of requiring doc archaeology.
"""

from __future__ import annotations

from typing import Any

from .command_registry import command_for_component

_SEVERITY_ORDER = {"blocking": 0, "warning": 1}

_FALLBACK_COMMAND = "./bin/telegram-doctor --profile maintenance --json"
_REPAIR_PLAN_COMMAND = "./bin/telegram-repair-plan --json"


def build_next_actions(doctor_report: dict[str, Any]) -> dict[str, Any]:
    findings = [
        item for item in doctor_report.get("findings", []) if isinstance(item, dict)
    ]
    findings.sort(key=lambda item: _SEVERITY_ORDER.get(str(item.get("severity")), 9))

    blocking_actions: list[dict[str, Any]] = []
    warning_actions: list[dict[str, Any]] = []
    for finding in findings:
        severity = str(finding.get("severity", "warning"))
        component = str(finding.get("component", "unknown"))
        spec = command_for_component(component)
        command = spec.example if spec is not None else _FALLBACK_COMMAND
        action = {
            "severity": severity,
            "component": component,
            "finding_id": finding.get("id"),
            "message": finding.get("message"),
            "command": command,
        }
        if severity == "blocking":
            blocking_actions.append(action)
        else:
            warning_actions.append(action)

    if blocking_actions:
        blocking_actions.append(
            {
                "severity": "blocking",
                "component": "repair_plan",
                "finding_id": "dry_run_repair_plan",
                "message": (
                    "Blocking findings present: inspect the dry-run repair plan "
                    "before applying anything"
                ),
                "command": _REPAIR_PLAN_COMMAND,
            }
        )
    actions = blocking_actions + warning_actions

    return {
        "status": doctor_report.get("status"),
        "summary": doctor_report.get("summary"),
        "next_actions": actions,
    }


def render_next_actions(report: dict[str, Any]) -> str:
    lines = [f"status: {report.get('status')}"]
    actions = report.get("next_actions", [])
    if not actions:
        lines.append("no action needed")
        return "\n".join(lines)
    for index, action in enumerate(actions, start=1):
        lines.append(
            f"{index}. [{action.get('severity')}] {action.get('component')}: "
            f"{action.get('message')}"
        )
        lines.append(f"   run: {action.get('command')}")
    return "\n".join(lines)
