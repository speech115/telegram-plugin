from telegram_control_plane.operator_status import build_operator_status, render_operator_status


def test_operator_status_reports_stale_feature_matrix(monkeypatch):
    registry = {
        "status": "ok",
        "summary": {"blocking_findings": 0, "warning_findings": 0},
        "components": {
            "mcp_surface": {"status": "ok"},
            "mcp_telemetry": {"status": "ok"},
            "agent_docs_sync": {"status": "ok"},
        },
    }
    monkeypatch.setattr(
        "telegram_control_plane.operator_status.refresh_feature_status",
        lambda *, registry, write: {"changed_count": 1},
    )
    monkeypatch.setattr(
        "telegram_control_plane.operator_status.audit_runtime_compat",
        lambda: {"status": "ok"},
    )

    report = build_operator_status(registry=registry)

    assert report["status"] == "warn"
    assert report["summary"]["feature_status_changed_count"] == 1
    assert "Feature spreadsheet" in render_operator_status(report)


def test_operator_status_is_ok_when_all_checks_pass(monkeypatch):
    registry = {
        "status": "ok",
        "summary": {"blocking_findings": 0, "warning_findings": 0},
        "components": {
            "mcp_surface": {"status": "ok"},
            "mcp_telemetry": {"status": "ok"},
            "agent_docs_sync": {"status": "ok"},
        },
    }
    monkeypatch.setattr(
        "telegram_control_plane.operator_status.refresh_feature_status",
        lambda *, registry, write: {"changed_count": 0},
    )
    monkeypatch.setattr(
        "telegram_control_plane.operator_status.audit_runtime_compat",
        lambda: {"status": "ok"},
    )

    report = build_operator_status(registry=registry)

    assert report["status"] == "ok"
    assert report["next_action"] == "No action needed."
