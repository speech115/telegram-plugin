from __future__ import annotations

import pytest

from telegram_control_plane.doctor import ControlPlaneDoctor


def test_control_plane_doctor_builds_registry_from_component_reports() -> None:
    doctor = ControlPlaneDoctor(
        component_collector=lambda: {
            "mcp_surface": {"status": "ok", "findings": []},
            "telecrawl": {
                "status": "warn",
                "findings": [{"id": "telecrawl_known_gaps", "severity": "warn"}],
            },
        }
    )

    registry = doctor.build_registry()

    assert registry["read_only_external_state"] is True
    assert registry["status"] == "warn"
    assert registry["summary"]["components"] == {"mcp_surface": "ok", "telecrawl": "warn"}
    assert registry["summary"]["blocking_findings"] == 0
    assert registry["summary"]["warning_findings"] == 1
    assert registry["findings"] == [
        {"id": "telecrawl_known_gaps", "severity": "warn", "component": "telecrawl"}
    ]


def test_control_plane_doctor_write_registry_fails_closed_on_private_leak(tmp_path) -> None:
    doctor = ControlPlaneDoctor()

    with pytest.raises(ValueError, match="private runtime leaks"):
        doctor.write_registry(tmp_path / "observed-registry.json", {"note": "Telegram @example"})
