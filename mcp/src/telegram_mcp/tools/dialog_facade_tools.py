"""High-level dialog facade tools for common Telegram workflows."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from mcp.types import ToolAnnotations

from .. import runtime
from ..errors import ToolContractError, tool_error_handler
from ..intent_router import assert_live_result_data_source, enforce_live_read_route
from ..facade_limits import (
    FAST_CONTEXT_RECENT_LIMIT,
    FAST_DIALOG_READ_LIMIT,
    FAST_MEMBER_EXPORT_LIMIT,
    FAST_SEARCH_LIMIT,
    clamp_context_recent_limit,
    clamp_dialog_read_limit,
    clamp_member_export_limit,
    clamp_search_limit,
)
from ..member_export_paths import resolve_member_export_dir
from ..types import DialogPostCountResult, ParticipantsResult

READONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True)
ADDITIVE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True)
CONFIRMED_WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True)


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
    page_size: int = FAST_DIALOG_READ_LIMIT,
    offset_id: int = 0,
    include_voice_transcription: bool = False,
    max_voice_transcriptions: int | None = None,
    include_sender_name: bool = False,
):
    """Read a live Telegram dialog within one date window. Voice notes use Telegram built-in transcription."""
    page_size = clamp_dialog_read_limit(
        page_size,
        include_voice_transcription=include_voice_transcription,
        include_sender_name=include_sender_name,
    )
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
    limit: int = FAST_DIALOG_READ_LIMIT,
    offset_id: int = 0,
    include_voice_transcription: bool = False,
    max_voice_transcriptions: int | None = None,
    include_sender_name: bool = False,
):
    """Read one live Telegram dialog for one calendar day."""
    limit = clamp_dialog_read_limit(
        limit,
        include_voice_transcription=include_voice_transcription,
        include_sender_name=include_sender_name,
    )
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
    limit: int = FAST_DIALOG_READ_LIMIT,
    offset_id: int = 0,
    include_voice_transcription: bool = False,
    max_voice_transcriptions: int | None = None,
    include_sender_name: bool = False,
):
    """Read recent live Telegram dialog context. Voice notes use Telegram built-in transcription."""
    limit = clamp_dialog_read_limit(
        limit,
        include_voice_transcription=include_voice_transcription,
        include_sender_name=include_sender_name,
    )
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
    limit: int = FAST_DIALOG_READ_LIMIT,
    offset_id: int = 0,
    include_voice_transcription: bool = False,
    max_voice_transcriptions: int | None = None,
    include_sender_name: bool = False,
):
    """App-style alias: read one day when day is provided, otherwise recent context."""
    limit = clamp_dialog_read_limit(
        limit,
        include_voice_transcription=include_voice_transcription,
        include_sender_name=include_sender_name,
    )
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
    recent_limit: int = FAST_CONTEXT_RECENT_LIMIT,
    date_from: str | None = None,
    date_to: str | None = None,
    offset_id: int = 0,
    include_pinned: bool = False,
    pinned_limit: int = 5,
    include_voice_transcription: bool | None = None,
    max_voice_transcriptions: int | None = None,
):
    """Collect live dialog evidence for agent work without sending anything."""
    recent_limit = clamp_context_recent_limit(recent_limit, mode=mode)
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
    recent_limit: int = FAST_CONTEXT_RECENT_LIMIT,
    date_from: str | None = None,
    date_to: str | None = None,
    offset_id: int = 0,
    include_pinned: bool = False,
    pinned_limit: int = 5,
    include_voice_transcription: bool | None = None,
    max_voice_transcriptions: int | None = None,
):
    """App-style alias for collect_dialog_context."""
    recent_limit = clamp_context_recent_limit(recent_limit, mode=mode)
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


async def search_dialog_messages(
    chat: str | int,
    query: str,
    limit: int = FAST_SEARCH_LIMIT,
    include_sender_name: bool = False,
):
    """Search within one live Telegram dialog."""
    limit = clamp_search_limit(limit)
    tg = await runtime.get_tg()
    return await tg.search_dialog_messages(
        chat=chat,
        query=query,
        limit=limit,
        include_sender_name=include_sender_name,
    )


async def telegram_read(
    chat: str | int,
    day: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = FAST_DIALOG_READ_LIMIT,
    mode: str = "fast",
):
    """Task-shaped Telegram read entrypoint for common natural-language requests."""
    intent = enforce_live_read_route(
        tool_name="telegram_read",
        day=day,
        date_from=date_from,
        date_to=date_to,
    )
    include_sender_name = mode.strip().lower() == "full"
    limit = clamp_dialog_read_limit(
        limit,
        include_voice_transcription=False,
        include_sender_name=include_sender_name,
    )
    recent_limit = clamp_context_recent_limit(limit, mode=mode)
    tg = await runtime.get_tg()
    if date_from or date_to:
        result = await tg.collect_dialog_context(
            chat=chat,
            mode=mode,
            recent_limit=recent_limit,
            date_from=date_from,
            date_to=date_to,
            include_pinned=False,
            include_voice_transcription=False,
        )
        assert_live_result_data_source(result.model_dump(mode="json"), tool_name="telegram_read", intent=intent)
        return result
    if day:
        result = await tg.read_today_dialog(
            chat=chat,
            day=day,
            limit=limit,
            include_voice_transcription=False,
            include_sender_name=include_sender_name,
        )
        assert_live_result_data_source(result.model_dump(mode="json"), tool_name="telegram_read", intent="today")
        return result
    result = await tg.collect_dialog_context(
        chat=chat,
        mode=mode,
        recent_limit=recent_limit,
        include_pinned=False,
        include_voice_transcription=False,
    )
    assert_live_result_data_source(result.model_dump(mode="json"), tool_name="telegram_read", intent="recent")
    return result


async def telegram_search(chat: str | int, query: str, limit: int = FAST_SEARCH_LIMIT):
    """Task-shaped Telegram search entrypoint."""
    enforce_live_read_route(tool_name="telegram_search", explicit_intent="live_search")
    limit = clamp_search_limit(limit)
    tg = await runtime.get_tg()
    result = await tg.search_dialog_messages(
        chat=chat,
        query=query,
        limit=limit,
        include_sender_name=False,
    )
    assert_live_result_data_source(result.model_dump(mode="json"), tool_name="telegram_search", intent="live_search")
    return result


async def telegram_count_posts(chat: str | int) -> DialogPostCountResult:
    """Return total visible posts/messages in a dialog without downloading history."""
    enforce_live_read_route(tool_name="telegram_count_posts", explicit_intent="live_read")
    tg = await runtime.get_tg()
    result = await tg.count_dialog_posts(chat=chat)
    assert_live_result_data_source(
        result.model_dump(mode="json"),
        tool_name="telegram_count_posts",
        intent="live_read",
    )
    return result


async def telegram_export_members(
    chat: str | int,
    limit: int = FAST_MEMBER_EXPORT_LIMIT,
    filter: str = "all",
    output_dir: str | None = None,
):
    """Export channel/group members to a private local JSON artifact."""
    limit = clamp_member_export_limit(limit)
    tg = await runtime.get_tg()
    handle = await tg.resolve_dialog(chat)
    if filter == "admins":
        participants = await tg.get_admins(chat=handle.dialog_ref)
        total = len(participants)
    elif filter == "banned":
        participants = await tg.get_banned_users(chat=handle.dialog_ref)
        total = len(participants)
    else:
        participants, total = await tg.get_participants(chat=handle.dialog_ref, limit=limit)

    export_dir = resolve_member_export_dir(output_dir)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    export_path = export_dir / f"members-{handle.id}-{stamp}.json"
    export_path.write_text(
        json.dumps(
            {
                "chat": handle.model_dump(mode="json"),
                "filter": filter,
                "total": total,
                "exported_count": len(participants),
                "participants": [item.model_dump(mode="json") for item in participants],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return ParticipantsResult(
        participants=participants,
        total=total,
        export_path=str(export_path),
    )


async def telegram_prepare_reply(
    chat: str | int,
    goal: str,
    reply_to_message_id: int | None = None,
    context_limit: int = 20,
    mode: str = "fast",
    draft_text: str | None = None,
):
    """Task-shaped reply preparation entrypoint. This never sends."""
    tg = await runtime.get_tg()
    return await tg.prepare_dialog_reply(
        chat=chat,
        goal=goal,
        reply_to_message_id=reply_to_message_id,
        context_limit=context_limit,
        mode=mode,
        draft_text=draft_text,
    )


async def telegram_confirmed_send(
    confirmation_token: str | None = None,
    preview_id: str | None = None,
    chat: str | int | None = None,
    text: str | None = None,
    message_id: int | None = None,
    parse_mode: str = "md",
):
    """Task-shaped confirmed send/reply entrypoint backed by preview tokens."""
    if not preview_id and not confirmation_token:
        raise ToolContractError(
            "missing_confirmation_token",
            "telegram_confirmed_send requires preview_id or confirmation_token from prepare_*",
        )
    tg = await runtime.get_tg()
    return await tg._commit_confirmed_send(
        preview_id=preview_id,
        confirmation_token=confirmation_token,
        chat=chat,
        text=text,
        parse_mode=parse_mode,
        message_id=message_id,
    )


async def telegram_send(
    chat: str | int,
    text: str,
    parse_mode: str = "md",
):
    """Task-shaped direct send entrypoint. Sends immediately on the local owner daemon."""
    tg = await runtime.get_tg()
    return await tg.send_message(
        chat=chat,
        text=text,
        parse_mode=parse_mode or None,
    )


async def send_dialog_message(
    chat: str | int,
    text: str,
    parse_mode: str = "md",
    confirmation_token: str | None = None,
):
    """Send a message through the dialog facade."""
    tg = await runtime.get_tg()
    return await tg.send_dialog_message(
        chat=chat,
        text=text,
        parse_mode=parse_mode,
        confirmation_token=confirmation_token,
    )


async def reply_in_dialog(
    chat: str | int,
    message_id: int,
    text: str,
    parse_mode: str = "md",
    confirmation_token: str | None = None,
):
    """Reply to one message through the dialog facade."""
    tg = await runtime.get_tg()
    return await tg.reply_in_dialog(
        chat=chat,
        message_id=message_id,
        text=text,
        parse_mode=parse_mode,
        confirmation_token=confirmation_token,
    )


async def reply_message(
    chat: str | int,
    message_id: int,
    text: str,
    parse_mode: str = "md",
    confirmation_token: str | None = None,
):
    """App-style alias for reply_in_dialog."""
    tg = await runtime.get_tg()
    return await tg.reply_in_dialog(
        chat=chat,
        message_id=message_id,
        text=text,
        parse_mode=parse_mode,
        confirmation_token=confirmation_token,
    )


def register(
    mcp,
    *,
    include_writes: bool = False,
    include_legacy_reads: bool = False,
    include_legacy_facade: bool = False,
) -> None:
    mcp.tool(annotations=READONLY)(tool_error_handler(resolve_dialog))
    mcp.tool(annotations=READONLY)(tool_error_handler(find_dialog))
    if include_legacy_reads:
        mcp.tool(annotations=READONLY)(tool_error_handler(read_dialog_by_date))
        mcp.tool(annotations=READONLY)(tool_error_handler(read_today_dialog))
        mcp.tool(annotations=READONLY)(tool_error_handler(read_recent_dialog))
        mcp.tool(annotations=READONLY)(tool_error_handler(read_dialog))
    mcp.tool(annotations=READONLY)(tool_error_handler(collect_dialog_context))
    mcp.tool(annotations=READONLY)(tool_error_handler(collect_context))
    if include_legacy_facade:
        mcp.tool(annotations=READONLY)(tool_error_handler(prepare_dialog_reply))
        mcp.tool(annotations=READONLY)(tool_error_handler(draft_reply))
        mcp.tool(annotations=READONLY)(tool_error_handler(prepare_send_message))
        mcp.tool(annotations=READONLY)(tool_error_handler(prepare_reply_message))
        mcp.tool(annotations=READONLY)(tool_error_handler(search_dialog_messages))
    mcp.tool(annotations=READONLY)(tool_error_handler(telegram_read))
    mcp.tool(annotations=READONLY)(tool_error_handler(telegram_search))
    mcp.tool(annotations=READONLY)(tool_error_handler(telegram_count_posts))
    mcp.tool(annotations=READONLY)(tool_error_handler(telegram_export_members))
    mcp.tool(annotations=READONLY)(tool_error_handler(telegram_prepare_reply))
    mcp.tool(annotations=CONFIRMED_WRITE)(tool_error_handler(telegram_confirmed_send))
    if include_writes:
        mcp.tool(annotations=ADDITIVE)(tool_error_handler(telegram_send))
        mcp.tool(annotations=ADDITIVE)(tool_error_handler(send_dialog_message))
        mcp.tool(annotations=ADDITIVE)(tool_error_handler(reply_in_dialog))
        mcp.tool(annotations=ADDITIVE)(tool_error_handler(reply_message))
