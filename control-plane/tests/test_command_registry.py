from __future__ import annotations

import json
from pathlib import Path

import pytest

from telegram_control_plane.command_registry import (
    COMMAND_REGISTRY,
    LEVELS,
    SAFETIES,
    command_for_component,
    registry_report,
)

ROOT = Path(__file__).resolve().parents[1]
BIN_DIR = ROOT / "bin"

# Helper sourced by other wrappers, not an operator command.
NON_COMMAND_BIN = {"telegram-env.sh"}


def bin_wrapper_names() -> set[str]:
    return {
        path.name
        for path in BIN_DIR.iterdir()
        if path.is_file()
        and not path.name.startswith(".")
        and path.name not in NON_COMMAND_BIN
    }


def test_every_bin_wrapper_is_registered() -> None:
    registered = {spec.name for spec in COMMAND_REGISTRY}
    assert bin_wrapper_names() == registered


def test_every_bin_wrapper_is_executable() -> None:
    for name in bin_wrapper_names():
        mode = (BIN_DIR / name).stat().st_mode
        assert mode & 0o111, name


def test_registry_entries_are_valid() -> None:
    seen: set[str] = set()
    for spec in COMMAND_REGISTRY:
        assert spec.name not in seen, f"duplicate registry entry: {spec.name}"
        seen.add(spec.name)
        assert spec.level in LEVELS, spec.name
        assert spec.safety in SAFETIES, spec.name
        assert spec.purpose, spec.name
        assert spec.example.startswith(("./bin/", "tg ")), spec.name
        assert (BIN_DIR / spec.name).exists(), spec.name


def test_registry_report_shape() -> None:
    report = registry_report()
    assert report["status"] == "ok"
    names = [entry["name"] for entry in report["commands"]]
    assert "telegram-doctor" in names
    assert "tg" in names
    # JSON-serializable end to end.
    json.dumps(report)


@pytest.mark.parametrize(
    ("component", "expected"),
    [
        ("mcp_surface", "telegram-mcp-surface"),
        ("source_routing", "telegram-source-routing-audit"),
        ("launchd", "telegram-launchd-audit"),
        ("sessions", "telegram-session-audit"),
        ("plugin_drift", "telegram-plugin-drift"),
        ("mcp_telemetry", "telegram-telemetry-status"),
        ("telecrawl", "telegram-telecrawl-status"),
        ("docs", "telegram-docs-audit"),
        ("managed_systems", "telegram-managed-systems"),
        ("telegram_mirror", "telegram-mirror-audit"),
        ("runtime_inventory", "telegram-runtime-inventory"),
        ("api_gap_audit", "telegram-api-gap-audit"),
        ("mirror_fast_status", "telegram-mirror-fast"),
        ("golden_read_smoke", "telegram-golden-read-smoke"),
        ("release_gates", "telegram-release-gates"),
        ("mcp_profiles", "telegram-mcp-profiles"),
    ],
)
def test_doctor_components_map_to_drilldown_commands(component: str, expected: str) -> None:
    spec = command_for_component(component)
    assert spec is not None
    assert spec.name == expected


def test_all_doctor_profile_components_have_drilldown_mapping() -> None:
    from telegram_control_plane.doctor_profiles import PROFILE_COMPONENTS

    for components in PROFILE_COMPONENTS.values():
        for component in components:
            assert command_for_component(component) is not None, component


def test_agents_md_documents_daily_and_live_commands() -> None:
    agents_md = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    for spec in COMMAND_REGISTRY:
        if spec.level in {"daily", "live"}:
            assert spec.name in agents_md, (
                f"AGENTS.md must mention {spec.level} command {spec.name}"
            )
