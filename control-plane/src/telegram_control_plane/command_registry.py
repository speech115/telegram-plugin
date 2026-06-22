"""Compatibility adapter for the control-plane command catalog."""

from __future__ import annotations

from typing import Any

from .catalog import (
    LEVELS,
    SAFETIES,
    COMMAND_SPECS as COMMAND_REGISTRY,
    CommandSpec,
    ControlPlaneCatalog,
)

_CATALOG = ControlPlaneCatalog.default()


def command_for_component(component: str) -> CommandSpec | None:
    return _CATALOG.command_for_component(component)


def command_by_name(name: str) -> CommandSpec | None:
    return _CATALOG.command_by_name(name)


def registry_report() -> dict[str, Any]:
    return _CATALOG.registry_report()
