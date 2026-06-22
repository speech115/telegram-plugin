from __future__ import annotations

from telegram_control_plane.catalog import ControlPlaneCatalog
from telegram_control_plane.command_registry import COMMAND_REGISTRY
from telegram_control_plane.doctor_profiles import PROFILE_COMPONENTS


def test_catalog_is_single_source_for_commands_and_profiles() -> None:
    catalog = ControlPlaneCatalog.default()

    assert tuple(catalog.commands()) == COMMAND_REGISTRY
    assert catalog.profile_components("core") == PROFILE_COMPONENTS["core"]
    assert catalog.profile_components("maintenance") == PROFILE_COMPONENTS["maintenance"]


def test_every_profile_component_has_catalog_metadata() -> None:
    catalog = ControlPlaneCatalog.default()

    for profile in catalog.profile_names():
        for component in catalog.profile_components(profile):
            spec = catalog.component(component)
            assert spec is not None, component
            assert spec.id == component
            if spec.command_name is not None:
                assert catalog.command_by_name(spec.command_name) is not None, component


def test_catalog_maps_components_to_commands_without_raw_registry_scan() -> None:
    catalog = ControlPlaneCatalog.default()

    assert catalog.command_for_component("mcp_surface").name == "telegram-mcp-surface"
    assert catalog.command_for_component("runtime_compat").name == "telegram-runtime-compat"
    assert catalog.command_for_component("unknown") is None
