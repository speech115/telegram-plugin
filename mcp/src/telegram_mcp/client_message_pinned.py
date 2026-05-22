"""Pinned message read operations for TelegramWrapper."""

from __future__ import annotations

from .client_message_caps import MessageCapResult as _MessageCapResult
from .client_message_common import _FetchedMessageRecord, _MessageCollectionStats
from .types import MessageInfo
from .utils import get_media_type


class MessagePinnedMixin:
    """Pinned message helpers."""

    async def _get_pinned_messages_with_caps(
        self, chat: str | int, limit: int = 50, include_sender_name: bool = True
    ) -> _MessageCapResult:
        return await self._dedupe_read_call(
            ("get_pinned_messages_with_caps", chat, limit, include_sender_name),
            lambda: self._get_pinned_messages_with_caps_uncached(
                chat=chat,
                limit=limit,
                include_sender_name=include_sender_name,
            ),
        )

    async def _get_pinned_messages_with_caps_uncached(
        self, chat: str | int, limit: int = 50, include_sender_name: bool = True
    ) -> _MessageCapResult:
        self._validate_non_negative("limit", limit)
        entity = await self._resolve_entity(chat)
        from telethon.tl.types import InputMessagesFilterPinned

        if limit <= 0:
            return _MessageCapResult(messages=[])

        fetch_limit, request_was_capped = self._bounded_read_limit(limit)

        async def fetch_pinned_messages() -> tuple[list[_FetchedMessageRecord], bool]:
            records = []
            async for msg in self.client.iter_messages(
                entity, limit=fetch_limit + 1, filter=InputMessagesFilterPinned()
            ):
                if len(records) >= fetch_limit:
                    return records, True
                records.append(
                    _FetchedMessageRecord(
                        message=msg,
                        media_type=get_media_type(msg),
                    )
                )
            return records, False

        records, has_more = await self._run_read(
            "get_pinned_messages",
            fetch_pinned_messages,
        )
        stats = _MessageCollectionStats()
        messages = await self._enrich_message_records(
            entity=entity,
            peer=entity,
            records=records,
            include_voice_transcription=False,
            max_voice_transcriptions=0,
            include_sender_name=include_sender_name,
            stats=stats,
        )
        initial_reasons = ["message_limit"] if request_was_capped and has_more else []
        return self._apply_message_caps(
            messages,
            initial_reasons=initial_reasons,
            sender_resolution_count=stats.sender_resolution_count,
        )

    async def get_pinned_messages(
        self, chat: str | int, limit: int = 50
    ) -> list[MessageInfo]:
        return await self._dedupe_read_call(
            ("get_pinned_messages", chat, limit),
            lambda: self._get_pinned_messages_uncached(chat=chat, limit=limit),
        )

    async def _get_pinned_messages_uncached(
        self, chat: str | int, limit: int = 50
    ) -> list[MessageInfo]:
        result = await self._get_pinned_messages_with_caps(chat=chat, limit=limit)
        return result.messages
