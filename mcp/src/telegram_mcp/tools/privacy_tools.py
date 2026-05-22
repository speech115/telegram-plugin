"""Privacy and notification settings tools."""

from __future__ import annotations

from mcp.types import ToolAnnotations

from .. import runtime
from ..errors import tool_error_handler
from ..types import OperationResult

ADDITIVE_IDEMPOTENT = ToolAnnotations(
    readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=True
)


async def set_chat_muted(chat: str | int, muted: bool = True) -> OperationResult:
    """Mute or unmute notifications for a chat."""
    tg = await runtime.get_tg()
    if muted:
        await tg.mute_chat(chat=chat)
        return OperationResult(message="Chat muted")
    else:
        await tg.unmute_chat(chat=chat)
        return OperationResult(message="Chat unmuted")


async def set_chat_archived(chat: str | int, archived: bool = True) -> OperationResult:
    """Archive or unarchive a chat."""
    tg = await runtime.get_tg()
    if archived:
        await tg.archive_chat(chat=chat)
        return OperationResult(message="Chat archived")
    else:
        await tg.unarchive_chat(chat=chat)
        return OperationResult(message="Chat unarchived")


def register(mcp) -> None:
    mcp.tool(annotations=ADDITIVE_IDEMPOTENT)(tool_error_handler(set_chat_muted))
    mcp.tool(annotations=ADDITIVE_IDEMPOTENT)(tool_error_handler(set_chat_archived))
