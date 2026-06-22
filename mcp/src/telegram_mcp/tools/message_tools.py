"""Message mutation and retrieval tools."""

from __future__ import annotations

from mcp.types import ToolAnnotations

from .. import runtime
from ..errors import tool_error_handler
from ..types import (
    DialogSliceResult,
    LinkResult,
    MessageInfo,
    MessagesResult,
    OperationResult,
    PollInfo,
    TranscriptionResult,
)

READONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True)
ADDITIVE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True)
DESTRUCTIVE = ToolAnnotations(readOnlyHint=False, destructiveHint=True, openWorldHint=True)
IDEMPOTENT = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=True)


async def list_messages(
    chat: str | int,
    limit: int = 20,
    offset_id: int = 0,
    min_id: int = 0,
    max_id: int = 0,
    include_voice_transcription: bool = False,
    max_voice_transcriptions: int | None = None,
    include_sender_name: bool = True,
) -> MessagesResult:
    """Get messages from a chat with pagination. chat: numeric ID, @username, phone, or 'me'."""
    tg = await runtime.get_tg()
    result = await tg.read_dialog_slice(
        chat=chat,
        limit=limit,
        offset_id=offset_id,
        min_id=min_id,
        max_id=max_id,
        include_voice_transcription=include_voice_transcription,
        max_voice_transcriptions=max_voice_transcriptions,
        include_sender_name=include_sender_name,
    )
    return MessagesResult(
        messages=result.messages,
        voice_transcription_status=result.voice_transcription_status,
        voice_transcription_count=result.voice_transcription_count,
        omitted_voice_count=result.omitted_voice_count,
        sender_resolution_count=result.sender_resolution_count,
        truncated=result.truncated,
        truncated_reason=result.truncated_reason,
    )


async def read_dialog_slice(
    chat: str | int,
    limit: int = 20,
    offset_id: int = 0,
    min_id: int = 0,
    max_id: int = 0,
    include_voice_transcription: bool = False,
    max_voice_transcriptions: int | None = None,
    include_sender_name: bool = True,
    date_from: str | None = None,
    date_to: str | None = None,
) -> DialogSliceResult:
    """Get lightweight chat info and a message slice in one MCP call."""
    tg = await runtime.get_tg()
    return await tg.read_dialog_slice(
        chat=chat,
        limit=limit,
        offset_id=offset_id,
        min_id=min_id,
        max_id=max_id,
        include_voice_transcription=include_voice_transcription,
        max_voice_transcriptions=max_voice_transcriptions,
        include_sender_name=include_sender_name,
        date_from=date_from,
        date_to=date_to,
    )


async def search_messages(
    query: str,
    chat: str | int | None = None,
    limit: int = 20,
    include_sender_name: bool = True,
) -> MessagesResult:
    """Search messages by text, globally or in a specific chat."""
    tg = await runtime.get_tg()
    result = await tg._search_messages_with_caps(
        query=query,
        chat=chat,
        limit=limit,
        include_sender_name=include_sender_name,
    )
    return MessagesResult(
        messages=result.messages,
        sender_resolution_count=result.sender_resolution_count,
        truncated=result.truncated,
        truncated_reason=result.truncated_reason,
    )


async def global_search(
    query: str,
    limit: int = 20,
    include_sender_name: bool = True,
) -> MessagesResult:
    """Search messages across all available chats."""
    tg = await runtime.get_tg()
    result = await tg.global_search(
        query=query,
        limit=limit,
        include_sender_name=include_sender_name,
    )
    return MessagesResult(
        messages=result.messages,
        sender_resolution_count=result.sender_resolution_count,
        truncated=result.truncated,
        truncated_reason=result.truncated_reason,
    )


async def sent_media_search(
    media_type: str = "photo_video",
    query: str | None = None,
    limit: int = 20,
    max_dialogs: int = 20,
    include_sender_name: bool = True,
) -> MessagesResult:
    """Find outgoing media messages across recent chats. media_type: photo_video/photo/video/document/gif/audio/voice."""
    tg = await runtime.get_tg()
    result = await tg.sent_media_search(
        media_type=media_type,
        query=query,
        limit=limit,
        max_dialogs=max_dialogs,
        include_sender_name=include_sender_name,
    )
    return MessagesResult(
        messages=result.messages,
        sender_resolution_count=result.sender_resolution_count,
        truncated=result.truncated,
        truncated_reason=result.truncated_reason,
    )


async def send_message(
    chat: str | int,
    text: str,
    parse_mode: str = "md",
) -> MessageInfo:
    """Send a message to a chat."""
    tg = await runtime.get_tg()
    return await tg.send_message(chat=chat, text=text, parse_mode=parse_mode or None)


async def reply_to_message(
    chat: str | int,
    message_id: int,
    text: str,
    parse_mode: str = "md",
) -> MessageInfo:
    """Reply to a specific message in a chat."""
    tg = await runtime.get_tg()
    return await tg.reply_to_message(
        chat=chat,
        message_id=message_id,
        text=text,
        parse_mode=parse_mode or None,
    )


async def edit_message(
    chat: str | int,
    message_id: int,
    text: str,
    parse_mode: str = "md",
) -> MessageInfo:
    """Edit your own message."""
    tg = await runtime.get_tg()
    return await tg.edit_message(
        chat=chat,
        message_id=message_id,
        text=text,
        parse_mode=parse_mode or None,
    )


async def delete_messages(
    chat: str | int,
    message_ids: list[int],
    revoke: bool = True,
) -> OperationResult:
    """Delete messages from a chat."""
    tg = await runtime.get_tg()
    count = await tg.delete_messages(chat=chat, message_ids=message_ids, revoke=revoke)
    return OperationResult(message=f"Deleted {count} message(s)")


async def forward_messages(
    from_chat: str | int,
    to_chat: str | int,
    message_ids: list[int],
) -> MessagesResult:
    """Forward messages from one chat to another."""
    tg = await runtime.get_tg()
    msgs = await tg.forward_messages(
        from_chat=from_chat, to_chat=to_chat, message_ids=message_ids
    )
    return MessagesResult(messages=msgs)


async def set_message_pinned(
    chat: str | int,
    message_id: int,
    pinned: bool = True,
    notify: bool = False,
) -> OperationResult:
    """Pin or unpin a message in a chat."""
    tg = await runtime.get_tg()
    if pinned:
        await tg.pin_message(chat=chat, message_id=message_id, notify=notify)
        return OperationResult(message=f"Message {message_id} pinned")
    else:
        await tg.unpin_message(chat=chat, message_id=message_id)
        return OperationResult(message=f"Message {message_id} unpinned")


async def transcribe_voice(chat: str | int, message_id: int) -> TranscriptionResult:
    """Transcribe a voice/video message using Telegram Premium built-in transcription."""
    tg = await runtime.get_tg()
    return await tg.transcribe_voice(chat=chat, message_id=message_id)


async def send_reaction(
    chat: str | int,
    message_id: int,
    emoji: str,
) -> OperationResult:
    """React to a message with an emoji."""
    tg = await runtime.get_tg()
    await tg.send_reaction(chat=chat, message_id=message_id, emoji=emoji)
    return OperationResult(message=f"Reacted with {emoji}")


async def mark_as_read(chat: str | int) -> OperationResult:
    """Mark all messages in a chat as read."""
    tg = await runtime.get_tg()
    await tg.mark_as_read(chat=chat)
    return OperationResult(message="Chat marked as read")


async def get_message_link(chat: str | int, message_id: int) -> LinkResult:
    """Get a t.me link to a specific message."""
    tg = await runtime.get_tg()
    link = await tg.get_message_link(chat=chat, message_id=message_id)
    return LinkResult(link=link)


async def create_poll(
    chat: str | int,
    question: str,
    options: list[str],
    multiple_choice: bool = False,
    quiz_mode: bool = False,
    correct_option: int | None = None,
    public_voters: bool = True,
) -> PollInfo:
    """Create a poll or quiz in a chat."""
    tg = await runtime.get_tg()
    return await tg.create_poll(
        chat=chat,
        question=question,
        options=options,
        multiple_choice=multiple_choice,
        quiz_mode=quiz_mode,
        correct_option=correct_option,
        public_voters=public_voters,
    )


async def get_pinned_messages(
    chat: str | int, limit: int = 50
) -> MessagesResult:
    """Get all pinned messages in a chat."""
    tg = await runtime.get_tg()
    result = await tg._get_pinned_messages_with_caps(chat=chat, limit=limit)
    return MessagesResult(
        messages=result.messages,
        sender_resolution_count=result.sender_resolution_count,
        truncated=result.truncated,
        truncated_reason=result.truncated_reason,
    )


async def send_voice(chat: str | int, file_path: str) -> MessageInfo:
    """Send a voice message (.ogg/.opus file)."""
    tg = await runtime.get_tg()
    return await tg.send_voice(chat=chat, file_path=file_path)


async def send_message_with_buttons(
    chat: str | int,
    text: str,
    buttons: list[list[dict[str, str]]],
    parse_mode: str = "md",
) -> MessageInfo:
    """Send a message with inline keyboard buttons."""
    tg = await runtime.get_tg()
    return await tg.send_message_with_buttons(
        chat=chat,
        text=text,
        buttons=buttons,
        parse_mode=parse_mode or None,
    )


def register(mcp, *, facade_only: bool = False) -> None:
    if facade_only:
        mcp.tool(annotations=READONLY)(tool_error_handler(transcribe_voice))
        return

    mcp.tool(annotations=READONLY)(tool_error_handler(list_messages))
    mcp.tool(annotations=READONLY)(tool_error_handler(read_dialog_slice))
    mcp.tool(annotations=READONLY)(tool_error_handler(search_messages))
    mcp.tool(annotations=READONLY)(tool_error_handler(global_search))
    mcp.tool(annotations=READONLY)(tool_error_handler(sent_media_search))
    mcp.tool(annotations=ADDITIVE)(tool_error_handler(send_message))
    mcp.tool(annotations=ADDITIVE)(tool_error_handler(reply_to_message))
    mcp.tool(annotations=DESTRUCTIVE)(tool_error_handler(edit_message))
    mcp.tool(annotations=DESTRUCTIVE)(tool_error_handler(delete_messages))
    mcp.tool(annotations=ADDITIVE)(tool_error_handler(forward_messages))
    mcp.tool(annotations=ADDITIVE)(tool_error_handler(set_message_pinned))
    mcp.tool(annotations=READONLY)(tool_error_handler(transcribe_voice))
    mcp.tool(annotations=ADDITIVE)(tool_error_handler(send_reaction))
    mcp.tool(annotations=IDEMPOTENT)(tool_error_handler(mark_as_read))
    mcp.tool(annotations=READONLY)(tool_error_handler(get_message_link))
    mcp.tool(annotations=ADDITIVE)(tool_error_handler(create_poll))
    mcp.tool(annotations=READONLY)(tool_error_handler(get_pinned_messages))
    mcp.tool(annotations=ADDITIVE)(tool_error_handler(send_voice))
    mcp.tool(annotations=ADDITIVE)(tool_error_handler(send_message_with_buttons))
