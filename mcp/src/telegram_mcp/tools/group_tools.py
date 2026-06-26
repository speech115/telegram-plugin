"""Group and channel management tools."""

from __future__ import annotations

from mcp.types import ToolAnnotations

from .. import runtime
from ..errors import ToolContractError, tool_error_handler
from ..types import ChatInfo, InviteLinkInfo, OperationResult, ParticipantsResult

READONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True)
ADDITIVE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True)
DESTRUCTIVE = ToolAnnotations(readOnlyHint=False, destructiveHint=True, openWorldHint=True)
PARTICIPANT_FILTERS = {"all", "admins", "banned"}


def _normalize_participant_filter(filter_value: str) -> str:
    normalized = filter_value.strip().lower()
    if normalized not in PARTICIPANT_FILTERS:
        raise ToolContractError(
            "invalid_input",
            "participant filter must be one of: all, admins, banned",
        )
    return normalized


async def create_group(title: str, user_ids: list[int]) -> ChatInfo:
    """Create a new group chat with given members."""
    tg = await runtime.get_tg()
    return await tg.create_group(title=title, user_ids=user_ids)


async def create_channel(
    title: str, about: str = "", megagroup: bool = False
) -> ChatInfo:
    """Create a new channel or supergroup."""
    tg = await runtime.get_tg()
    return await tg.create_channel(title=title, about=about, megagroup=megagroup)


async def edit_chat_title(chat: str | int, title: str) -> OperationResult:
    """Change the title of a group, supergroup, or channel."""
    tg = await runtime.get_tg()
    await tg.edit_chat_title(chat=chat, title=title)
    return OperationResult(message=f"Title changed to: {title}")


async def delete_chat_photo(chat: str | int) -> OperationResult:
    """Delete the photo of a group, supergroup, or channel."""
    tg = await runtime.get_tg()
    await tg.delete_chat_photo(chat=chat)
    return OperationResult(message="Chat photo deleted")


async def leave_chat(chat: str | int) -> OperationResult:
    """Leave a group or channel."""
    tg = await runtime.get_tg()
    await tg.leave_chat(chat=chat)
    return OperationResult(message="Left the chat")


async def get_participants(
    chat: str | int, limit: int = 200, filter: str = "all"
) -> ParticipantsResult:
    """Get members of a group or channel (filter: 'all', 'admins', 'banned')."""
    tg = await runtime.get_tg()
    filter = _normalize_participant_filter(filter)
    if filter == "admins":
        participants = await tg.get_admins(chat=chat, limit=limit)
        return ParticipantsResult(participants=participants, total=len(participants))
    elif filter == "banned":
        participants = await tg.get_banned_users(chat=chat, limit=limit)
        return ParticipantsResult(participants=participants, total=len(participants))
    else:
        participants, total = await tg.get_participants(chat=chat, limit=limit)
        return ParticipantsResult(participants=participants, total=total)


async def promote_admin(
    chat: str | int,
    user_id: int,
    rights: dict[str, bool] | None = None,
) -> OperationResult:
    """Promote a user to admin in a channel/supergroup."""
    tg = await runtime.get_tg()
    await tg.promote_admin(chat=chat, user_id=user_id, rights=rights)
    return OperationResult(message=f"User {user_id} promoted to admin")


async def demote_admin(chat: str | int, user_id: int) -> OperationResult:
    """Remove admin rights from a user in a channel/supergroup."""
    tg = await runtime.get_tg()
    await tg.demote_admin(chat=chat, user_id=user_id)
    return OperationResult(message=f"User {user_id} demoted from admin")


async def set_user_banned(
    chat: str | int, user_id: int, banned: bool = True
) -> OperationResult:
    """Ban or unban a user in a group or channel."""
    tg = await runtime.get_tg()
    if banned:
        await tg.ban_user(chat=chat, user_id=user_id)
        return OperationResult(message=f"User {user_id} banned")
    else:
        await tg.unban_user(chat=chat, user_id=user_id)
        return OperationResult(message=f"User {user_id} unbanned")


async def get_invite_link(chat: str | int) -> InviteLinkInfo:
    """Get or create an invite link for a chat."""
    tg = await runtime.get_tg()
    return await tg.get_invite_link(chat=chat)


async def invite_to_group(
    chat: str | int, user_ids: list[int]
) -> OperationResult:
    """Invite users to a group or channel."""
    tg = await runtime.get_tg()
    await tg.invite_to_group(chat=chat, user_ids=user_ids)
    return OperationResult(message=f"Invited {len(user_ids)} user(s)")


def register(mcp) -> None:
    mcp.tool(annotations=DESTRUCTIVE)(tool_error_handler(create_group))
    mcp.tool(annotations=DESTRUCTIVE)(tool_error_handler(create_channel))
    mcp.tool(annotations=DESTRUCTIVE)(tool_error_handler(edit_chat_title))
    mcp.tool(annotations=DESTRUCTIVE)(tool_error_handler(delete_chat_photo))
    mcp.tool(annotations=DESTRUCTIVE)(tool_error_handler(leave_chat))
    mcp.tool(annotations=READONLY)(tool_error_handler(get_participants))
    mcp.tool(annotations=DESTRUCTIVE)(tool_error_handler(promote_admin))
    mcp.tool(annotations=DESTRUCTIVE)(tool_error_handler(demote_admin))
    mcp.tool(annotations=DESTRUCTIVE)(tool_error_handler(set_user_banned))
    mcp.tool(annotations=ADDITIVE)(tool_error_handler(get_invite_link))
    mcp.tool(annotations=ADDITIVE)(tool_error_handler(invite_to_group))
