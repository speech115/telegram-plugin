"""Read-only reaction analytics tools."""

from __future__ import annotations

from mcp.types import ToolAnnotations

from .. import runtime
from ..errors import tool_error_handler
from ..types import MessageReactionsResult, UnreadReactionsResult

READONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True)


async def get_message_reactions(
    chat: str | int,
    message_id: int,
    limit: int = 50,
    reaction: str | None = None,
    offset: str | None = None,
) -> MessageReactionsResult:
    """Get reaction counts and visible reactors for one message."""
    tg = await runtime.get_tg()
    return await tg.get_message_reactions(
        chat=chat,
        message_id=message_id,
        limit=limit,
        reaction=reaction,
        offset=offset,
    )


async def get_unread_reactions(
    chat: str | int,
    limit: int = 20,
    offset_id: int = 0,
    min_id: int = 0,
    max_id: int = 0,
    topic_id: int | None = None,
    include_sender_name: bool = True,
) -> UnreadReactionsResult:
    """Get messages that have unread reactions without marking reactions read."""
    tg = await runtime.get_tg()
    return await tg.get_unread_reactions(
        chat=chat,
        limit=limit,
        offset_id=offset_id,
        min_id=min_id,
        max_id=max_id,
        topic_id=topic_id,
        include_sender_name=include_sender_name,
    )


def register(mcp) -> None:
    mcp.tool(annotations=READONLY)(tool_error_handler(get_message_reactions))
    mcp.tool(annotations=READONLY)(tool_error_handler(get_unread_reactions))
