"""User and runtime health tools."""

from __future__ import annotations

import os

from mcp.types import ToolAnnotations

from .. import runtime
from ..errors import tool_error_handler
from ..types import DoctorInfo, HealthInfo, UserInfo

READONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True)


async def get_me() -> UserInfo:
    """Get information about the current Telegram user."""
    tg = await runtime.get_tg()
    return await tg.get_me()


async def health_check() -> HealthInfo:
    """Get connection and session health for the Telegram MCP runtime."""
    tg = await runtime.get_tg()
    health = await tg.health_check()
    return health.model_copy(update={"shared_client": runtime.shared_mode_enabled()})


async def doctor_check() -> DoctorInfo:
    """Run a deeper runtime diagnostic for session, transport and connectivity."""
    tg = await runtime.get_tg()
    return await tg.doctor_check()


def register(mcp) -> None:
    mcp.tool(annotations=READONLY)(tool_error_handler(get_me))
    mcp.tool(annotations=READONLY)(tool_error_handler(doctor_check))

    if os.getenv("TELEGRAM_MCP_INCLUDE_DIAGNOSTICS", "").lower() in {"1", "true", "yes"}:
        mcp.tool(annotations=READONLY)(tool_error_handler(health_check))
