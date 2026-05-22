"""User profile management tools."""

from __future__ import annotations

from mcp.types import ToolAnnotations

from .. import runtime
from ..errors import tool_error_handler
from ..types import OperationResult, UserPhotosResult, UserStatus

READONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True)
DESTRUCTIVE = ToolAnnotations(readOnlyHint=False, destructiveHint=True, openWorldHint=True)


async def update_profile(
    first_name: str | None = None,
    last_name: str | None = None,
    about: str | None = None,
) -> OperationResult:
    """Update your Telegram profile (name and/or bio)."""
    tg = await runtime.get_tg()
    await tg.update_profile(first_name=first_name, last_name=last_name, about=about)
    return OperationResult(message="Profile updated")


async def delete_profile_photo() -> OperationResult:
    """Delete your current profile photo."""
    tg = await runtime.get_tg()
    await tg.delete_profile_photo()
    return OperationResult(message="Profile photo deleted")


async def get_user_photos(user_id: int, limit: int = 10) -> UserPhotosResult:
    """Get profile photos of a user."""
    tg = await runtime.get_tg()
    photos, total = await tg.get_user_photos(user_id=user_id, limit=limit)
    return UserPhotosResult(photos=photos, total=total)


async def get_user_status(user_id: int) -> UserStatus:
    """Get online status of a user."""
    tg = await runtime.get_tg()
    return await tg.get_user_status(user_id=user_id)


def register(mcp) -> None:
    mcp.tool(annotations=DESTRUCTIVE)(tool_error_handler(update_profile))
    mcp.tool(annotations=DESTRUCTIVE)(tool_error_handler(delete_profile_photo))
    mcp.tool(annotations=READONLY)(tool_error_handler(get_user_photos))
    mcp.tool(annotations=READONLY)(tool_error_handler(get_user_status))
