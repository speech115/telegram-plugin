from __future__ import annotations

import csv
from pathlib import Path

from telegram_control_plane.feature_status import refresh_feature_status


FIELDNAMES = [
    "feature_id",
    "feature_name",
    "verification_command",
    "command_name",
    "host_status",
    "status",
    "last_result",
    "errors",
    "next_action",
    "optimization_verdict",
    "expected_failure_class",
]


def write_rows(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_refresh_feature_status_dry_run_reports_updates_without_writing(tmp_path: Path) -> None:
    path = tmp_path / "feature-status.csv"
    write_rows(
        path,
        [
            {
                "feature_id": "CLI-014",
                "feature_name": "Plugin drift audit",
                "verification_command": "./bin/telegram-plugin-drift --json",
                "command_name": "telegram-plugin-drift",
                "host_status": "fail",
                "status": "tested_fail",
                "last_result": "old",
                "errors": "old_error",
                "next_action": "old action",
                "optimization_verdict": "blocked",
                "expected_failure_class": "old_failure",
            }
        ],
    )
    registry = {
        "status": "ok",
        "generated_at": "2026-06-22T07:00:00Z",
        "components": {"plugin_drift": {"status": "ok", "findings": []}},
    }

    report = refresh_feature_status(path=path, registry=registry, write=False)

    assert report["status"] == "ok"
    assert report["changed_rows"] == ["CLI-014"]
    assert read_rows(path)[0]["host_status"] == "fail"


def test_refresh_feature_status_write_updates_component_rows(tmp_path: Path) -> None:
    path = tmp_path / "feature-status.csv"
    write_rows(
        path,
        [
            {
                "feature_id": "CLI-014",
                "feature_name": "Plugin drift audit",
                "verification_command": "./bin/telegram-plugin-drift --json",
                "command_name": "telegram-plugin-drift",
                "host_status": "fail",
                "status": "tested_fail",
                "last_result": "old",
                "errors": "old_error",
                "next_action": "old action",
                "optimization_verdict": "blocked",
                "expected_failure_class": "old_failure",
            }
        ],
    )
    registry = {
        "status": "ok",
        "generated_at": "2026-06-22T07:00:00Z",
        "components": {"plugin_drift": {"status": "ok", "findings": []}},
    }

    report = refresh_feature_status(path=path, registry=registry, write=True)
    row = read_rows(path)[0]

    assert report["changed_rows"] == ["CLI-014"]
    assert row["host_status"] == "pass"
    assert row["status"] == "tested_pass"
    assert row["last_result"] == "plugin_drift ok"
    assert row["errors"] == ""
    assert row["next_action"] == "keep covered"
    assert row["optimization_verdict"] == "acceptable"
    assert row["expected_failure_class"] == "none"
