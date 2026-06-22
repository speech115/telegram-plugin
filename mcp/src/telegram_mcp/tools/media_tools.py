"""Media transfer tools."""

from __future__ import annotations

from mcp.types import ToolAnnotations

from .. import runtime
from ..errors import tool_error_handler
from ..types import MediaBatchResult, MediaInfo, MediaInspectionManifest, MessageInfo

READONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True)
ADDITIVE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True)


async def download_media(chat: str | int, message_id: int) -> MediaInfo:
    """Download media from a message to local filesystem."""
    tg = await runtime.get_tg()
    return await tg.download_media(chat=chat, message_id=message_id)


async def download_media_batch(
    chat: str | int,
    message_ids: list[int],
    concurrency: int = 2,
) -> MediaBatchResult:
    """Download multiple message media files with one message lookup."""
    tg = await runtime.get_tg()
    return await tg.download_media_batch(
        chat=chat,
        message_ids=message_ids,
        concurrency=concurrency,
    )


async def download_dialog_media(
    chat: str | int,
    message_ids: list[int],
    concurrency: int = 2,
) -> MediaBatchResult:
    """Download dialog media by message IDs. Thin alias over download_media_batch."""
    tg = await runtime.get_tg()
    return await tg.download_media_batch(
        chat=chat,
        message_ids=message_ids,
        concurrency=concurrency,
    )


async def prepare_media_inspection_manifest(
    chat: str | int,
    limit: int = 50,
    offset_id: int = 0,
    date_from: str | None = None,
    date_to: str | None = None,
) -> MediaInspectionManifest:
    """Prepare media metadata from a dialog slice without downloading files."""
    tg = await runtime.get_tg()
    return await tg.prepare_media_inspection_manifest(
        chat=chat,
        limit=limit,
        offset_id=offset_id,
        date_from=date_from,
        date_to=date_to,
    )


async def telegram_inspect_media(
    chat: str | int,
    limit: int = 30,
    offset_id: int = 0,
    date_from: str | None = None,
    date_to: str | None = None,
) -> MediaInspectionManifest:
    """Task-shaped media inspection manifest. This does not download files."""
    tg = await runtime.get_tg()
    return await tg.prepare_media_inspection_manifest(
        chat=chat,
        limit=limit,
        offset_id=offset_id,
        date_from=date_from,
        date_to=date_to,
    )


async def download_story_media(peer: str | int, story_id: int) -> MediaInfo:
    """Download media from a Telegram story to local filesystem."""
    tg = await runtime.get_tg()
    return await tg.download_story_media(peer=peer, story_id=story_id)


async def send_file(
    chat: str | int,
    file_path: str,
    caption: str = "",
    parse_mode: str = "md",
) -> MessageInfo:
    """Send a file to a chat."""
    tg = await runtime.get_tg()
    return await tg.send_file(
        chat=chat,
        file_path=file_path,
        caption=caption,
        parse_mode=parse_mode or None,
    )


def register(mcp) -> None:
    register_facade(mcp)
    mcp.tool(annotations=READONLY)(tool_error_handler(download_story_media))
    mcp.tool(annotations=ADDITIVE)(tool_error_handler(send_file))


def register_facade(mcp) -> None:
    mcp.tool(annotations=READONLY)(tool_error_handler(download_media))
    mcp.tool(annotations=READONLY)(tool_error_handler(download_media_batch))
    mcp.tool(annotations=READONLY)(tool_error_handler(download_dialog_media))
    mcp.tool(annotations=READONLY)(tool_error_handler(prepare_media_inspection_manifest))
    mcp.tool(annotations=READONLY)(tool_error_handler(telegram_inspect_media))
    # notes-runner assemble delivery uses digest-runner send-file -> MCP send_file.
    mcp.tool(annotations=ADDITIVE)(tool_error_handler(send_file))
