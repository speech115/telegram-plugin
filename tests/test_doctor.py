from __future__ import annotations

import pytest

import telegram_control_plane.audits as audits
import telegram_control_plane.cli as cli
import telegram_control_plane.runtime_inventory as runtime_inventory
import telegram_control_plane.source_routing as source_routing
from telegram_control_plane.doctor import ControlPlaneDoctor
from telegram_control_plane.doctor_profiles import CORE_COMPONENTS, MAINTENANCE_COMPONENTS


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
    assert registry["profile"] == "core"
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


def test_core_doctor_collects_only_core_components(monkeypatch) -> None:
    calls: list[str] = []

    def report(name: str):
        def collect() -> dict[str, object]:
            calls.append(name)
            return {"status": "ok", "findings": []}

        return collect

    for name in (
        "audit_fast_read_adapter",
        "audit_mcp_surface",
        "audit_launchd",
        "audit_sessions",
        "audit_mirror_fast_status",
    ):
        monkeypatch.setattr(audits, name, report(name.removeprefix("audit_")))
    monkeypatch.setattr(source_routing, "audit_source_routing", report("source_routing"))

    for name in (
        "audit_managed_systems",
        "audit_docs",
        "audit_plugin_drift",
        "audit_mcp_telemetry",
        "audit_golden_read_smoke",
        "audit_agent_docs_sync",
        "audit_release_gates",
        "audit_install_adapters",
        "audit_mcp_profiles",
        "audit_mirror",
        "audit_telecrawl",
    ):
        monkeypatch.setattr(
            audits,
            name,
            lambda *args, _name=name, **kwargs: (_ for _ in ()).throw(AssertionError(_name)),
        )
    monkeypatch.setattr(
        runtime_inventory,
        "audit_runtime_inventory",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("runtime_inventory")),
    )

    registry = ControlPlaneDoctor(profile="core").build_registry()

    assert registry["profile"] == "core"
    assert set(registry["summary"]["components"]) == set(CORE_COMPONENTS)
    assert set(calls) == set(CORE_COMPONENTS)


def test_maintenance_doctor_collects_maintenance_components(monkeypatch) -> None:
    def report(name: str):
        def collect(*args, **kwargs) -> dict[str, object]:
            return {"status": "ok", "findings": [], "name": name}

        return collect

    for name in (
        "audit_managed_systems",
        "audit_docs",
        "audit_plugin_drift",
        "audit_mcp_telemetry",
        "audit_fast_read_adapter",
        "audit_golden_read_smoke",
        "audit_agent_docs_sync",
        "audit_release_gates",
        "audit_install_adapters",
        "audit_mcp_surface",
        "audit_mcp_profiles",
        "audit_launchd",
        "audit_sessions",
        "audit_mirror",
        "audit_mirror_fast_status",
        "audit_telecrawl",
    ):
        monkeypatch.setattr(audits, name, report(name.removeprefix("audit_")))
    monkeypatch.setattr(source_routing, "audit_source_routing", report("source_routing"))
    monkeypatch.setattr(runtime_inventory, "audit_runtime_inventory", report("runtime_inventory"))

    registry = ControlPlaneDoctor(profile="maintenance").build_registry()

    assert registry["profile"] == "maintenance"
    assert set(registry["summary"]["components"]) == set(MAINTENANCE_COMPONENTS)
    assert "telecrawl" in registry["summary"]["components"]
    assert "release_gates" in registry["summary"]["components"]
    assert "runtime_inventory" in registry["summary"]["components"]


def test_control_plane_doctor_rejects_unknown_profile() -> None:
    with pytest.raises(ValueError, match="Unknown doctor profile"):
        ControlPlaneDoctor(profile="everything")


def test_cli_doctor_defaults_to_core_profile(monkeypatch, capsys) -> None:
    profiles: list[str] = []

    class FakeDoctor:
        def __init__(self, *, profile: str = "core") -> None:
            profiles.append(profile)

        def build_registry(self) -> dict[str, object]:
            return {
                "status": "ok",
                "profile": profiles[-1],
                "summary": {"components": {}, "blocking_findings": 0, "warning_findings": 0},
                "findings": [],
            }

        def write_registry(self, path, registry) -> None:
            raise AssertionError("registry should not be written with --no-write-registry")

    monkeypatch.setattr(cli, "ControlPlaneDoctor", FakeDoctor)

    assert cli.main(["doctor", "--json", "--no-write-registry"]) == 0
    payload = capsys.readouterr().out

    assert profiles == ["core"]
    assert '"profile": "core"' in payload


def test_cli_doctor_accepts_maintenance_profile(monkeypatch, capsys) -> None:
    profiles: list[str] = []

    class FakeDoctor:
        def __init__(self, *, profile: str = "core") -> None:
            profiles.append(profile)

        def build_registry(self) -> dict[str, object]:
            return {
                "status": "warn",
                "profile": profiles[-1],
                "summary": {"components": {"telecrawl": "warn"}, "blocking_findings": 0, "warning_findings": 1},
                "findings": [{"id": "telecrawl_known_gaps", "severity": "warn", "component": "telecrawl"}],
            }

        def write_registry(self, path, registry) -> None:
            raise AssertionError("registry should not be written with --no-write-registry")

    monkeypatch.setattr(cli, "ControlPlaneDoctor", FakeDoctor)

    assert cli.main(["doctor", "--profile", "maintenance", "--json", "--no-write-registry"]) == 0
    payload = capsys.readouterr().out

    assert profiles == ["maintenance"]
    assert '"profile": "maintenance"' in payload
    assert "telecrawl_known_gaps" in payload
