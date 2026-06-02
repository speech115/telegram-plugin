"""Media operations for TelegramWrapper."""

from __future__ import annotations

import asyncio
import os
import sqlite3
import time
from pathlib import Path
from typing import Any

import structlog
from telethon.tl.functions.stories import GetStoriesByIDRequest
from telethon.tl.types import MessageMediaPhoto, StoryItem

from .download_registry import DownloadRegistry
from .errors import ToolContractError
from .file_path_policy import validate_outbound_media_path
from .types import (
    MediaBatchItem,
    MediaBatchResult,
    MediaInfo,
    MediaInspectionManifest,
    MediaInspectionManifestItem,
    MessageInfo,
)
from .utils import get_media_type


class MediaOperationsMixin:
    """Download and upload media operations."""

    def _media_info_for_downloaded_message(self, msg: Any, path: str | None) -> MediaInfo:
        media_type = get_media_type(msg) or "unknown"
        file_name = Path(path).name if path else None
        file_size = None
        mime_type = None

        document = getattr(msg, "document", None)
        photo = getattr(msg, "photo", None)
        if document:
            file_size = document.size
            mime_type = document.mime_type
        elif photo:
            media_type = "photo"

        return MediaInfo(
            file_name=file_name,
            file_size=file_size,
            mime_type=mime_type,
            media_type=media_type,
            local_path=path,
        )

    def _media_manifest_metadata(
        self,
        msg: Any | None,
    ) -> tuple[str | None, str | None, int | None]:
        media_type = get_media_type(msg) if msg is not None else None
        mime_type = None
        file_size = None
        document = getattr(msg, "document", None) if msg is not None else None
        if document is not None:
            mime_type = getattr(document, "mime_type", None)
            file_size = getattr(document, "size", None)
        elif getattr(msg, "photo", None) is not None:
            media_type = "photo"
        return media_type, mime_type, file_size

    def _record_downloaded_message_media(
        self,
        *,
        chat_id: int | str,
        chat_ref: str,
        message_id: int,
        path: str | None,
    ) -> None:
        if not path:
            return

        try:
            DownloadRegistry(
                self.settings.media_download_registry_path,
            ).upsert_download(
                chat_id=chat_id,
                chat_ref=chat_ref,
                message_id=message_id,
                local_path=Path(path),
            )
        except (OSError, sqlite3.Error) as exc:
            structlog.get_logger().warning(
                "telegram_download_registry_failed",
                chat_id=str(chat_id),
                message_id=message_id,
                error=f"{type(exc).__name__}: {exc}",
            )

    def _known_local_media_path(self, *, chat_id: int | str, message_id: int) -> str | None:
        try:
            entry = DownloadRegistry(
                self.settings.media_download_registry_path,
            ).get(chat_id=chat_id, message_id=message_id)
        except (OSError, sqlite3.Error) as exc:
            structlog.get_logger().warning(
                "telegram_download_registry_lookup_failed",
                chat_id=str(chat_id),
                message_id=message_id,
                error=f"{type(exc).__name__}: {exc}",
            )
            return None
        if entry is None:
            return None
        path = Path(entry.local_path).expanduser()
        return str(path) if path.exists() else None

    async def prepare_media_inspection_manifest(
        self,
        chat: str | int,
        limit: int = 50,
        offset_id: int = 0,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> MediaInspectionManifest:
        """Return media metadata from a dialog slice without downloading files."""
        if date_from or date_to:
            if not date_from or not date_to:
                raise ToolContractError(
                    "invalid_date_range",
                    "date_from and date_to must be provided together",
                )
            read_result = await self.read_dialog_by_date(
                chat=chat,
                date_from=date_from,
                date_to=date_to,
                total_limit=limit,
                offset_id=offset_id,
                include_voice_transcription=False,
                include_sender_name=False,
            )
        else:
            read_result = await self.read_recent_dialog(
                chat=chat,
                limit=limit,
                offset_id=offset_id,
                include_voice_transcription=False,
                include_sender_name=False,
            )

        media_messages = [message for message in read_result.messages if message.has_media]
        raw_messages_by_id: dict[int, Any] = {}
        messages_needing_metadata = [
            message for message in media_messages if message.media_type is None
        ]
        if messages_needing_metadata:
            entity = await self._resolve_entity(self._coerce_dialog_query(chat))
            raw_messages = await self._run_read(
                "prepare_media_inspection_manifest_get_messages",
                lambda: self.client.get_messages(
                    entity,
                    ids=[message.id for message in messages_needing_metadata],
                ),
            )
            raw_message_list = (
                raw_messages if isinstance(raw_messages, list) else [raw_messages]
            )
            raw_messages_by_id = {
                msg.id: msg
                for msg in raw_message_list
                if msg is not None and getattr(msg, "id", None) is not None
            }

        items = []
        for message in media_messages:
            raw_message = raw_messages_by_id.get(message.id)
            media_type, mime_type, file_size = self._media_manifest_metadata(raw_message)
            local_path = self._known_local_media_path(
                chat_id=read_result.chat.id,
                message_id=message.id,
            )
            items.append(
                MediaInspectionManifestItem(
                    message_id=message.id,
                    chat_id=message.chat_id,
                    date=message.date,
                    caption=message.text or "",
                    media_type=media_type or message.media_type,
                    mime_type=mime_type or message.mime_type,
                    file_size=file_size or message.file_size,
                    local_path=local_path,
                )
            )

        return MediaInspectionManifest(
            chat=read_result.chat,
            range=read_result.range,
            requested_limit=limit,
            message_count=read_result.message_count,
            media_count=len(items),
            items=items,
            has_more_before=read_result.has_more_before,
            next_offset_id=read_result.next_offset_id,
            data_source=read_result.data_source,
        )

    async def _download_message_media(
        self,
        msg: Any,
        *,
        label: str,
        chat_id: int | str,
        chat_ref: str,
        message_id: int,
    ) -> MediaInfo:
        if not getattr(msg, "media", None):
            raise ValueError("message has no media")
        path = await self._run_media(
            label,
            lambda: self.client.download_media(
                msg,
                file=str(self.settings.download_dir) + "/",
            ),
        )
        self._record_downloaded_message_media(
            chat_id=chat_id,
            chat_ref=chat_ref,
            message_id=message_id,
            path=path,
        )
        return self._media_info_for_downloaded_message(msg, path)

    async def download_media(self, chat: str | int, message_id: int) -> MediaInfo:
        entity = await self._resolve_entity(chat)
        msgs = await self._run_media(
            "download_media_get_message",
            lambda: self.client.get_messages(entity, ids=message_id),
        )
        msg = msgs if not isinstance(msgs, list) else msgs[0] if msgs else None
        if not msg or not msg.media:
            raise ValueError(f"Message {message_id} has no media")

        self.settings.ensure_dirs()
        self._maybe_cleanup_download_dir()
        return await self._download_message_media(
            msg,
            label="download_media",
            chat_id=entity.id,
            chat_ref=str(chat),
            message_id=message_id,
        )

    async def download_media_batch(
        self,
        chat: str | int,
        message_ids: list[int],
        concurrency: int = 2,
    ) -> MediaBatchResult:
        self._validate_non_negative("concurrency", concurrency)
        if concurrency == 0:
            raise ToolContractError(
                "invalid_pagination",
                "concurrency must be greater than 0",
            )
        if not message_ids:
            entity = await self._resolve_entity(chat)
            return MediaBatchResult(
                chat_id=entity.id,
                requested_count=0,
                success_count=0,
                failed_count=0,
                items=[],
            )
        for message_id in message_ids:
            self._validate_non_negative("message_id", message_id)

        max_items = max(1, int(getattr(self.settings, "read_max_media_items", 25)))
        if len(message_ids) > max_items:
            raise ToolContractError(
                "media_batch_too_large",
                f"download_media_batch supports at most {max_items} message ids per call",
            )
        entity = await self._resolve_entity(chat)
        unique_message_ids = list(dict.fromkeys(message_ids))
        self._increment_runtime_stat(
            "download_media_batch_dedupe_count",
            len(message_ids) - len(unique_message_ids),
        )
        fetched = await self._run_media(
            "download_media_batch_get_messages",
            lambda: self.client.get_messages(entity, ids=unique_message_ids),
        )
        fetched_list = fetched if isinstance(fetched, list) else [fetched]
        messages_by_id = {
            msg.id: msg
            for msg in fetched_list
            if msg is not None and getattr(msg, "id", None) is not None
        }

        self.settings.ensure_dirs()
        self._maybe_cleanup_download_dir()
        scheduler_media_concurrency = max(
            1,
            int(getattr(self.settings, "scheduler_media_concurrency", 2)),
        )
        effective_concurrency = min(concurrency, scheduler_media_concurrency)
        self._set_runtime_stat(
            "download_media_batch_effective_concurrency",
            effective_concurrency,
        )
        local_semaphore = asyncio.Semaphore(effective_concurrency)

        async def download_one(message_id: int) -> MediaBatchItem:
            msg = messages_by_id.get(message_id)
            if msg is None:
                return MediaBatchItem(
                    message_id=message_id,
                    ok=False,
                    error="message_not_found",
                )
            if not getattr(msg, "media", None):
                return MediaBatchItem(
                    message_id=message_id,
                    ok=False,
                    error="message_has_no_media",
                )
            async with local_semaphore:
                try:
                    media = await self._download_message_media(
                        msg,
                        label="download_media_batch",
                        chat_id=entity.id,
                        chat_ref=str(chat),
                        message_id=message_id,
                    )
                    return MediaBatchItem(
                        message_id=message_id,
                        ok=True,
                        media=media,
                    )
                except Exception as exc:
                    return MediaBatchItem(
                        message_id=message_id,
                        ok=False,
                        error=f"{type(exc).__name__}: {exc}",
                    )

        unique_items = await asyncio.gather(
            *(download_one(mid) for mid in unique_message_ids),
        )
        items_by_id = {item.message_id: item for item in unique_items}
        items = [
            MediaBatchItem(
                message_id=items_by_id[mid].message_id,
                ok=items_by_id[mid].ok,
                media=items_by_id[mid].media,
                error=items_by_id[mid].error,
            )
            for mid in message_ids
        ]
        success_count = sum(1 for item in items if item.ok)
        return MediaBatchResult(
            chat_id=entity.id,
            requested_count=len(message_ids),
            success_count=success_count,
            failed_count=len(items) - success_count,
            items=items,
        )

    async def download_story_media(self, peer: str | int, story_id: int) -> MediaInfo:
        """Download media from a story by its ID."""
        entity = await self._resolve_entity(peer)
        input_peer = await self.client.get_input_entity(entity)
        result = await self._run_media(
            "download_story_media_get_story",
            lambda: self.client(GetStoriesByIDRequest(peer=input_peer, id=[story_id])),
        )
        story = None
        for item in result.stories:
            if isinstance(item, StoryItem):
                story = item
                break
        if not story or not story.media:
            raise ValueError(f"Story {story_id} has no media")

        self.settings.ensure_dirs()
        self._maybe_cleanup_download_dir()
        dest = str(self.settings.download_dir) + "/"

        log = structlog.get_logger()

        path = None
        try:
            path = await self._run_media(
                "download_story_media",
                lambda: self.client.download_media(story.media, file=dest),
            )
        except (TypeError, ValueError, AttributeError) as exc:
            log.debug("story_download_attempt1_failed", error=str(exc))

        if not path:
            try:
                path = await self._run_media(
                    "download_story_media_fallback",
                    lambda: self.client.download_media(story, file=dest),
                )
            except (TypeError, ValueError, AttributeError) as exc:
                log.debug("story_download_attempt2_failed", error=str(exc))

        if not path and isinstance(story.media, MessageMediaPhoto) and story.media.photo:
            try:
                from telethon.tl.types import InputPhotoFileLocation

                photo = story.media.photo
                largest = max(
                    photo.sizes,
                    key=lambda size: (
                        getattr(size, "w", 0) * getattr(size, "h", 0)
                        if hasattr(size, "w")
                        else 0
                    ),
                )
                loc = InputPhotoFileLocation(
                    id=photo.id,
                    access_hash=photo.access_hash,
                    file_reference=photo.file_reference,
                    thumb_size=getattr(largest, "type", "y"),
                )
                out_path = os.path.join(dest, f"story_{story_id}.jpg")
                with open(out_path, "wb") as handle:
                    async for chunk in self.client.iter_download(loc):
                        handle.write(chunk)
                if os.path.getsize(out_path) > 0:
                    path = out_path
                else:
                    os.remove(out_path)
            except (TypeError, ValueError, AttributeError, OSError) as exc:
                log.debug("story_download_attempt3_failed", error=str(exc))

        if not path:
            raise ValueError(
                f"Failed to download media from story {story_id}. "
                f"Media type: {type(story.media).__name__}"
            )

        media_type = "unknown"
        file_name = Path(path).name
        file_size = None
        mime_type = None

        if hasattr(story.media, "document") and story.media.document:
            doc = story.media.document
            file_size = doc.size
            mime_type = doc.mime_type
            media_type = (
                "video"
                if mime_type and mime_type.startswith("video")
                else "document"
            )
        elif hasattr(story.media, "photo") and story.media.photo:
            media_type = "photo"

        return MediaInfo(
            file_name=file_name,
            file_size=file_size,
            mime_type=mime_type,
            media_type=media_type,
            local_path=path,
        )

    async def send_file(
        self,
        chat: str,
        file_path: str,
        caption: str = "",
        parse_mode: str = "md",
    ) -> MessageInfo:
        safe_file_path = validate_outbound_media_path(file_path)
        entity = await self._resolve_entity(chat)
        started_at = time.perf_counter()
        self._append_write_audit_event(
            "send_file",
            "started",
            started_at,
            lane="media",
        )
        try:
            msg = await self._run_media(
                "send_file",
                lambda: self.client.send_file(
                    entity,
                    safe_file_path,
                    caption=caption,
                    parse_mode=parse_mode,
                ),
            )
        except BaseException as exc:
            self._append_write_audit_event(
                "send_file",
                "failed",
                started_at,
                lane="media",
                error=exc,
            )
            raise
        self._append_write_audit_event(
            "send_file",
            "succeeded",
            started_at,
            lane="media",
        )
        self._invalidate_after_dialog_write()
        return self._message_to_info(
            msg,
            default_chat_id=entity.id,
            is_outgoing=True,
            has_media=True,
        )
