from __future__ import annotations

from telegram_control_plane.runtime_inventory import audit_runtime_inventory


def test_runtime_inventory_aggregates_child_statuses() -> None:
    report = audit_runtime_inventory(
        launchd_report={"status": "ok", "findings": [], "loaded_jobs": []},
        sessions_report={"status": "ok", "findings": [], "summary": {"discovered": 1}},
        mirror_report={
            "status": "warn",
            "findings": [{"id": "mirror_runtime_exports_missing", "severity": "warn", "message": "missing"}],
            "runtime_state_summary": {"export_missing_count": 3, "export_ready_count": 0, "export_expected_count": 3},
        },
    )
    assert report["status"] == "warn"
    assert report["summary"]["launchd"]["status"] == "ok"
    assert report["summary"]["mirror_runtime"]["export_missing_count"] == 3
    assert any(item["component"] == "runtime_inventory/mirror_runtime" for item in report["findings"])


def test_runtime_inventory_blocks_when_launchd_fails() -> None:
    report = audit_runtime_inventory(
        launchd_report={"status": "fail", "findings": [{"id": "x", "severity": "blocking", "message": "bad"}]},
        sessions_report={"status": "ok", "findings": []},
        mirror_report={"status": "ok", "findings": []},
    )
    assert report["status"] == "fail"
    assert any(item["id"] == "runtime_inventory_child_failed" for item in report["findings"])