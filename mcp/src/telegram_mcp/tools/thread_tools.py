"""Thread, discussion, and forum topic tools."""

from __future__ import annotations

from mcp.types import ToolAnnotations

from .. import runtime
from ..errors import tool_error_handler
from ..types import ForumTopicsResult, ThreadMessagesResult

READONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True)


async def list_forum_topics(
    chat: str | int,
    limit: int = 20,
    q: str | None = None,
    offset_id: int = 0,
    offset_topic: int = 0,
) -> ForumTopicsResult:
    """List forum topics in a forum supergroup."""
    tg = await runtime.get_tg()
    return await tg.list_forum_topics(
        chat=chat,
        limit=limit,
        q=q,
        offset_id=offset_id,
        offset_topic=offset_topic,
    )


async def get_forum_topics_by_id(
    chat: str | int,
    topic_ids: list[int],
) -> ForumTopicsResult:
    """Get specific forum topics by topic IDs."""
    tg = await runtime.get_tg()
    return await tg.get_forum_topics_by_id(chat=chat, topic_ids=topic_ids)


async def get_discussion_message(
    chat: str | int,
    message_id: int,
    include_sender_name: bool = True,
) -> ThreadMessagesResult:
    """Get the linked discussion message for a channel post where Telegram exposes one."""
    tg = await runtime.get_tg()
    return await tg.get_discussion_message(
        chat=chat,
        message_id=message_id,
        include_sender_name=include_sender_name,
    )


async def get_thread_replies(
    chat: str | int,
    message_id: int,
    limit: int = 20,
    offset_id: int = 0,
    include_sender_name: bool = True,
) -> ThreadMessagesResult:
    """Read replies for one message or topic starter without marking them read."""
    tg = await runtime.get_tg()
    return await tg.get_thread_replies(
        chat=chat,
        message_id=message_id,
        limit=limit,
        offset_id=offset_id,
        include_sender_name=include_sender_name,
    )


def register(mcp) -> None:
    mcp.tool(annotations=READONLY)(tool_error_handler(list_forum_topics))
    mcp.tool(annotations=READONLY)(tool_error_handler(get_forum_topics_by_id))
    mcp.tool(annotations=READONLY)(tool_error_handler(get_discussion_message))
    mcp.tool(annotations=READONLY)(tool_error_handler(get_thread_replies))
