"""Message search operations for TelegramWrapper."""

from __future__ import annotations

import time
from typing import Any

from .client_message_caps import MessageCapResult as _MessageCapResult
from .client_message_common import _FetchedMessageRecord, _MessageCollectionStats
from .types import DialogReadRange, DialogReadResult, MessageInfo
from .utils import get_media_type


class MessageSearchMixin:
    """Global and dialog-scoped message search."""

    async def _search_messages_with_caps(
        self,
        query: str,
        chat: str | int | None = None,
        limit: int = 20,
        include_sender_name: bool = True,
    ) -> _MessageCapResult:
        return await self._dedupe_read_call(
            (
                "search_messages_with_caps",
                query,
                chat,
                limit,
                include_sender_name,
            ),
            lambda: self._search_messages_with_caps_uncached(
                query=query,
                chat=chat,
                limit=limit,
                include_sender_name=include_sender_name,
            ),
        )

    async def _search_messages_with_caps_uncached(
        self,
        query: str,
        chat: str | int | None = None,
        limit: int = 20,
        include_sender_name: bool = True,
    ) -> _MessageCapResult:
        started_at = time.perf_counter()
        self._validate_non_negative("limit", limit)
        entity = None
        if chat:
            entity = await self._resolve_entity(chat)

        if limit <= 0:
            return _MessageCapResult(messages=[])

        fetch_limit, request_was_capped = self._bounded_read_limit(limit)

        async def fetch_search_messages() -> tuple[list[_FetchedMessageRecord], bool]:
            records = []
            async for msg in self.client.iter_messages(
                entity, search=query, limit=fetch_limit + 1
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
            "search_messages",
            fetch_search_messages,
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
        self._emit_read_timing(
            "search_messages",
            started_at,
            item_count=len(messages),
            scoped=entity is not None,
            sender_resolution_count=stats.sender_resolution_count,
        )
        initial_reasons = ["message_limit"] if request_was_capped and has_more else []
        return self._apply_message_caps(
            messages,
            initial_reasons=initial_reasons,
            sender_resolution_count=stats.sender_resolution_count,
        )

    async def search_messages(
        self,
        query: str,
        chat: str | int | None = None,
        limit: int = 20,
        include_sender_name: bool = True,
    ) -> list[MessageInfo]:
        return await self._dedupe_read_call(
            (
                "search_messages",
                query,
                chat,
                limit,
                include_sender_name,
            ),
            lambda: self._search_messages_uncached(
                query=query,
                chat=chat,
                limit=limit,
                include_sender_name=include_sender_name,
            ),
        )

    async def _search_messages_uncached(
        self,
        query: str,
        chat: str | int | None = None,
        limit: int = 20,
        include_sender_name: bool = True,
    ) -> list[MessageInfo]:
        result = await self._search_messages_with_caps(
            query=query,
            chat=chat,
            limit=limit,
            include_sender_name=include_sender_name,
        )
        return result.messages

    async def search_dialog_messages(
        self,
        chat: str | int,
        query: str,
        limit: int = 20,
        include_sender_name: bool = True,
    ) -> DialogReadResult:
        cache_key = self._make_result_cache_key(
            "dialog_search",
            chat,
            query,
            limit,
            include_sender_name,
        )
        cached = self._dialog_read_cache_get(cache_key)
        if cached is not None:
            return cached

        return await self._dedupe_read_call(
            (
                "search_dialog_messages",
                chat,
                query,
                limit,
                include_sender_name,
            ),
            lambda: self._search_dialog_messages_cached(
                cache_key=cache_key,
                chat=chat,
                query=query,
                limit=limit,
                include_sender_name=include_sender_name,
            ),
        )

    async def _search_dialog_messages_cached(
        self,
        *,
        cache_key: str,
        chat: str | int,
        query: str,
        limit: int = 20,
        include_sender_name: bool = True,
    ) -> DialogReadResult:
        result = await self._search_dialog_messages_uncached(
            chat=chat,
            query=query,
            limit=limit,
            include_sender_name=include_sender_name,
        )
        self._dialog_read_cache_set(cache_key, result)
        return result

    async def _search_dialog_messages_uncached(
        self,
        chat: str | int,
        query: str,
        limit: int = 20,
        include_sender_name: bool = True,
    ) -> DialogReadResult:
        started_at = time.perf_counter()
        resolved_chat = self._coerce_dialog_query(chat)
        handle = await self.resolve_dialog(chat)
        search_result = await self._search_messages_with_caps(
            query=query,
            chat=resolved_chat,
            limit=limit,
            include_sender_name=include_sender_name,
        )
        result = DialogReadResult(
            chat=handle,
            messages=search_result.messages,
            message_count=len(search_result.messages),
            has_more_before=search_result.truncated,
            next_offset_id=None,
            range=DialogReadRange(),
            data_source="live_telegram",
            sender_resolution_count=search_result.sender_resolution_count,
            truncated=search_result.truncated,
            truncated_reason=search_result.truncated_reason,
        )
        self._emit_read_timing(
            "search_dialog_messages",
            started_at,
            item_count=result.message_count,
            truncated=result.truncated,
            truncated_reason=result.truncated_reason,
        )
        return result
