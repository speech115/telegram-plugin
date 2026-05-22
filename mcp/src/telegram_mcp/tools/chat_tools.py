"""Chat and identity resolution tools."""

from __future__ import annotations

from mcp.types import ToolAnnotations

from .. import runtime
from ..errors import tool_error_handler
from ..types import ChatInfo, Dialog, DialogsResult

READONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True)


async def list_chats(
    limit: int = 50,
    chat_type: str | None = None,
    unread_only: bool = False,
    archived: bool = False,
) -> DialogsResult:
    """List Telegram dialogs (chat: numeric ID, @username, phone, or "me")."""
    tg = await runtime.get_tg()
    dialogs = await tg.list_chats(
        limit=limit,
        chat_type=chat_type,
        unread_only=unread_only,
        archived=archived,
    )
    return DialogsResult(dialogs=dialogs)


async def get_chat_info(chat: str | int) -> ChatInfo:
    """Get detailed info about a chat."""
    tg = await runtime.get_tg()
    return await tg.get_chat_info(chat)


async def resolve_username(username: str) -> ChatInfo:
    """Resolve a @username to entity info."""
    tg = await runtime.get_tg()
    return await tg.resolve_username(username)


async def search_public_chats(query: str) -> DialogsResult:
    """Search for public chats, channels, and bots by name or username."""
    tg = await runtime.get_tg()
    results = await tg.search_public_chats(query=query)
    dialogs = [
        Dialog(
            id=r.id,
            name=r.name,
            type=r.type,
            username=r.username,
        )
        for r in results
    ]
    return DialogsResult(dialogs=dialogs)


def register(mcp) -> None:
    mcp.tool(annotations=READONLY)(tool_error_handler(list_chats))
    mcp.tool(annotations=READONLY)(tool_error_handler(get_chat_info))
    mcp.tool(annotations=READONLY)(tool_error_handler(resolve_username))
    mcp.tool(annotations=READONLY)(tool_error_handler(search_public_chats))
