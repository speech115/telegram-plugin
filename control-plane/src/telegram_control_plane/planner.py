"""Repair-plan planner facade; implementation lives in audit_remediation."""

from __future__ import annotations

from .audit_remediation import apply_repair_plan, build_repair_plan
from .paths import CONTROL_ROOT, MCP_REPO, PLUGIN_CACHE, PLUGIN_CACHE_ROOT, PLUGIN_SOURCE

AUTO_APPLY_STEP_IDS = frozenset({"plugin-cache-materialize"})

__all__ = [
    "AUTO_APPLY_STEP_IDS",
    "CONTROL_ROOT",
    "MCP_REPO",
    "PLUGIN_CACHE",
    "PLUGIN_CACHE_ROOT",
    "PLUGIN_SOURCE",
    "apply_repair_plan",
    "build_repair_plan",
]