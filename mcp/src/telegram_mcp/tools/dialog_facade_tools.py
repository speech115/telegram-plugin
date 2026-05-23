"""High-level dialog facade tools for common Telegram workflows."""

from __future__ import annotations

from mcp.types import ToolAnnotations

from .. import runtime
from ..errors import tool_error_handler

READONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True)
ADDITIVE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True)


async def resolve_dialog(query: str | int):
    """Resolve a dialog query into a reusable canonical dialog handle."""
    tg = await runtime.get_tg()
    return await tg.resolve_dialog(query)


async def find_dialog(query: str | int):
    """App-style alias for resolve_dialog."""
    tg = await runtime.get_tg()
    return await tg.resolve_dialog(query)


async def read_dialog_by_date(
    chat: str | int,
    date_from: str,
    date_to: str,
    page_size: int = 50,
    offset_id: int = 0,
    include_voice_transcription: bool = True,
    max_voice_transcriptions: int | None = None,
    include_sender_name: bool = True,
):
    """Read a live Telegram dialog within one date window. Voice notes use Telegram built-in transcription."""
    tg = await runtime.get_tg()
    return await tg.read_dialog_by_date(
        chat=chat,
        date_from=date_from,
        date_to=date_to,
        total_limit=page_size,
        offset_id=offset_id,
        include_voice_transcription=include_voice_transcription,
        max_voice_transcriptions=max_voice_transcriptions,
        include_sender_name=include_sender_name,
    )


async def read_today_dialog(
    chat: str | int,
    day: str | None = None,
    limit: int = 50,
    offset_id: int = 0,
    include_voice_transcription: bool = True,
    max_voice_transcriptions: int | None = None,
    include_sender_name: bool = True,
):
    """Read one live Telegram dialog for one calendar day."""
    tg = await runtime.get_tg()
    return await tg.read_today_dialog(
        chat=chat,
        day=day,
        limit=limit,
        offset_id=offset_id,
        include_voice_transcription=include_voice_transcription,
        max_voice_transcriptions=max_voice_transcriptions,
        include_sender_name=include_sender_name,
    )


async def read_recent_dialog(
    chat: str | int,
    limit: int = 50,
    offset_id: int = 0,
    include_voice_transcription: bool = True,
    max_voice_transcriptions: int | None = None,
    include_sender_name: bool = True,
):
    """Read recent live Telegram dialog context. Voice notes use Telegram built-in transcription."""
    tg = await runtime.get_tg()
    return await tg.read_recent_dialog(
        chat=chat,
        limit=limit,
        offset_id=offset_id,
        include_voice_transcription=include_voice_transcription,
        max_voice_transcriptions=max_voice_transcriptions,
        include_sender_name=include_sender_name,
    )


async def read_dialog(
    chat: str | int,
    day: str | None = None,
    limit: int = 50,
    offset_id: int = 0,
    include_voice_transcription: bool = True,
    max_voice_transcriptions: int | None = None,
    include_sender_name: bool = True,
):
    """App-style alias: read one day when day is provided, otherwise recent context."""
    tg = await runtime.get_tg()
    if day:
        return await tg.read_today_dialog(
            chat=chat,
            day=day,
            limit=limit,
            offset_id=offset_id,
            include_voice_transcription=include_voice_transcription,
            max_voice_transcriptions=max_voice_transcriptions,
            include_sender_name=include_sender_name,
        )
    return await tg.read_recent_dialog(
        chat=chat,
        limit=limit,
        offset_id=offset_id,
        include_voice_transcription=include_voice_transcription,
        max_voice_transcriptions=max_voice_transcriptions,
        include_sender_name=include_sender_name,
    )


async def collect_dialog_context(
    chat: str | int,
    mode: str = "fast",
    recent_limit: int = 50,
    date_from: str | None = None,
    date_to: str | None = None,
    offset_id: int = 0,
    include_pinned: bool = True,
    pinned_limit: int = 5,
    include_voice_transcription: bool | None = None,
    max_voice_transcriptions: int | None = None,
):
    """Collect live dialog evidence for agent work without sending anything."""
    tg = await runtime.get_tg()
    return await tg.collect_dialog_context(
        chat=chat,
        mode=mode,
        recent_limit=recent_limit,
        date_from=date_from,
        date_to=date_to,
        offset_id=offset_id,
        include_pinned=include_pinned,
        pinned_limit=pinned_limit,
        include_voice_transcription=include_voice_transcription,
        max_voice_transcriptions=max_voice_transcriptions,
    )


async def collect_context(
    chat: str | int,
    mode: str = "fast",
    recent_limit: int = 50,
    date_from: str | None = None,
    date_to: str | None = None,
    offset_id: int = 0,
    include_pinned: bool = True,
    pinned_limit: int = 5,
    include_voice_transcription: bool | None = None,
    max_voice_transcriptions: int | None = None,
):
    """App-style alias for collect_dialog_context."""
    tg = await runtime.get_tg()
    return await tg.collect_dialog_context(
        chat=chat,
        mode=mode,
        recent_limit=recent_limit,
        date_from=date_from,
        date_to=date_to,
        offset_id=offset_id,
        include_pinned=include_pinned,
        pinned_limit=pinned_limit,
        include_voice_transcription=include_voice_transcription,
        max_voice_transcriptions=max_voice_transcriptions,
    )


async def prepare_dialog_reply(
    chat: str | int,
    goal: str,
    reply_to_message_id: int | None = None,
    context_limit: int = 20,
    mode: str = "fast",
    draft_text: str | None = None,
):
    """Prepare a reply preview package. This never sends the message."""
    tg = await runtime.get_tg()
    return await tg.prepare_dialog_reply(
        chat=chat,
        goal=goal,
        reply_to_message_id=reply_to_message_id,
        context_limit=context_limit,
        mode=mode,
        draft_text=draft_text,
    )


async def draft_reply(
    chat: str | int,
    goal: str,
    reply_to_message_id: int | None = None,
    context_limit: int = 20,
    mode: str = "fast",
    draft_text: str | None = None,
):
    """App-style alias for prepare_dialog_reply. This never sends the message."""
    tg = await runtime.get_tg()
    return await tg.prepare_dialog_reply(
        chat=chat,
        goal=goal,
        reply_to_message_id=reply_to_message_id,
        context_limit=context_limit,
        mode=mode,
        draft_text=draft_text,
    )


async def prepare_send_message(
    chat: str | int,
    text: str,
    parse_mode: str = "md",
):
    """Prepare a send-message preview package. This never sends the message."""
    tg = await runtime.get_tg()
    return await tg.prepare_send_message(
        chat=chat,
        text=text,
        parse_mode=parse_mode,
    )


async def prepare_reply_message(
    chat: str | int,
    message_id: int,
    text: str,
    parse_mode: str = "md",
):
    """Prepare a reply preview package. This never sends the message."""
    tg = await runtime.get_tg()
    return await tg.prepare_reply_message(
        chat=chat,
        message_id=message_id,
        text=text,
        parse_mode=parse_mode,
    )


async def prepare_send_file(
    chat: str | int,
    file_path: str,
    caption: str = "",
    parse_mode: str = "md",
):
    """Prepare a file-send preview package. This validates path and never sends."""
    tg = await runtime.get_tg()
    return await tg.prepare_send_file(
        chat=chat,
        file_path=file_path,
        caption=caption,
        parse_mode=parse_mode,
    )


async def search_dialog_messages(
    chat: str | int,
    query: str,
    limit: int = 20,
    include_sender_name: bool = True,
):
    """Search within one live Telegram dialog."""
    tg = await runtime.get_tg()
    return await tg.search_dialog_messages(
        chat=chat,
        query=query,
        limit=limit,
        include_sender_name=include_sender_name,
    )


async def send_dialog_message(chat: str | int, text: str, parse_mode: str = "md"):
    """Send a message through the dialog facade."""
    tg = await runtime.get_tg()
    return await tg.send_dialog_message(chat=chat, text=text, parse_mode=parse_mode)


async def reply_in_dialog(
    chat: str | int,
    message_id: int,
    text: str,
    parse_mode: str = "md",
):
    """Reply to one message through the dialog facade."""
    tg = await runtime.get_tg()
    return await tg.reply_in_dialog(
        chat=chat,
        message_id=message_id,
        text=text,
        parse_mode=parse_mode,
    )


async def reply_message(
    chat: str | int,
    message_id: int,
    text: str,
    parse_mode: str = "md",
):
    """App-style alias for reply_in_dialog."""
    tg = await runtime.get_tg()
    return await tg.reply_in_dialog(
        chat=chat,
        message_id=message_id,
        text=text,
        parse_mode=parse_mode,
    )


def register(mcp, *, include_writes: bool = False) -> None:
    mcp.tool(annotations=READONLY)(tool_error_handler(resolve_dialog))
    mcp.tool(annotations=READONLY)(tool_error_handler(find_dialog))
    mcp.tool(annotations=READONLY)(tool_error_handler(read_dialog_by_date))
    mcp.tool(annotations=READONLY)(tool_error_handler(read_today_dialog))
    mcp.tool(annotations=READONLY)(tool_error_handler(read_recent_dialog))
    mcp.tool(annotations=READONLY)(tool_error_handler(read_dialog))
    mcp.tool(annotations=READONLY)(tool_error_handler(collect_dialog_context))
    mcp.tool(annotations=READONLY)(tool_error_handler(collect_context))
    mcp.tool(annotations=READONLY)(tool_error_handler(prepare_dialog_reply))
    mcp.tool(annotations=READONLY)(tool_error_handler(draft_reply))
    mcp.tool(annotations=READONLY)(tool_error_handler(prepare_send_message))
    mcp.tool(annotations=READONLY)(tool_error_handler(prepare_reply_message))
    mcp.tool(annotations=READONLY)(tool_error_handler(prepare_send_file))
    mcp.tool(annotations=READONLY)(tool_error_handler(search_dialog_messages))
    if include_writes:
        mcp.tool(annotations=ADDITIVE)(tool_error_handler(send_dialog_message))
        mcp.tool(annotations=ADDITIVE)(tool_error_handler(reply_in_dialog))
        mcp.tool(annotations=ADDITIVE)(tool_error_handler(reply_message))
