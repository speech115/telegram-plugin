from __future__ import annotations

import json

from telegram_control_plane.next_actions import build_next_actions


def _doctor_report(findings: list[dict[str, object]], status: str) -> dict[str, object]:
    return {
        "status": status,
        "findings": findings,
        "summary": {
            "blocking_findings": sum(
                1 for item in findings if item.get("severity") == "blocking"
            ),
            "warning_findings": sum(
                1 for item in findings if item.get("severity") == "warning"
            ),
        },
    }


def test_healthy_report_yields_no_actions() -> None:
    report = build_next_actions(_doctor_report([], "ok"))
    assert report["status"] == "ok"
    assert report["next_actions"] == []
    json.dumps(report)


def test_warning_maps_component_to_drilldown_command() -> None:
    doctor = _doctor_report(
        [
            {
                "severity": "warning",
                "component": "mcp_telemetry",
                "id": "tool_errors",
                "message": "recent tool errors",
            }
        ],
        "warn",
    )
    report = build_next_actions(doctor)
    assert report["status"] == "warn"
    (action,) = report["next_actions"]
    assert action["component"] == "mcp_telemetry"
    assert "telegram-telemetry-status" in action["command"]


def test_blocking_findings_come_first_and_add_repair_plan() -> None:
    doctor = _doctor_report(
        [
            {
                "severity": "warning",
                "component": "telecrawl",
                "id": "known_gaps",
                "message": "archive gaps",
            },
            {
                "severity": "blocking",
                "component": "mcp_surface",
                "id": "unexpected_write_tool",
                "message": "raw write tool exposed",
            },
        ],
        "fail",
    )
    report = build_next_actions(doctor)
    assert report["status"] == "fail"
    severities = [item["severity"] for item in report["next_actions"]]
    assert severities == sorted(severities, key=lambda s: 0 if s == "blocking" else 1)
    first = report["next_actions"][0]
    assert first["component"] == "mcp_surface"
    # Blocking findings must route through the dry-run repair plan.
    assert any(
        "telegram-repair-plan" in item["command"] for item in report["next_actions"]
    )


def test_unknown_component_falls_back_to_doctor() -> None:
    doctor = _doctor_report(
        [
            {
                "severity": "warning",
                "component": "mystery_component",
                "id": "x",
                "message": "?",
            }
        ],
        "warn",
    )
    report = build_next_actions(doctor)
    (action,) = report["next_actions"]
    assert "telegram-doctor" in action["command"]
