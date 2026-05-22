"""MCP resources for static/cacheable Telegram data."""

from __future__ import annotations

from .runtime import get_tg, mcp


@mcp.resource(
    "telegram://me",
    name="current_user",
    description="Current Telegram user info",
    mime_type="application/json",
)
async def me_resource() -> dict[str, object]:
    tg = await get_tg()
    info = await tg.get_me()
    return info.model_dump(mode="json")
