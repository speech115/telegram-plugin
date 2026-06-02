"""Dialog-level cached read helpers for TelegramWrapper."""

from __future__ import annotations

import time
from datetime import date

from .types import DialogReadRange, DialogReadResult


class MessageDialogReadMixin:
    """Agent-facing dialog read helpers built on read_dialog_slice."""

    async def _read_dialog_core(
        self,
        *,
        chat: str | int,
        limit: int,
        offset_id: int = 0,
        date_from: str | None = None,
        date_to: str | None = None,
        include_voice_transcription: bool = False,
        max_voice_transcriptions: int | None = None,
        include_sender_name: bool = False,
    ) -> DialogReadResult:
        self._validate_non_negative("limit", limit)
        self._validate_non_negative("offset_id", offset_id)
        resolved_chat = self._coerce_dialog_query(chat)
        handle, entity = await self._resolve_dialog_with_entity(chat)
        peer = await self._resolve_input_entity(handle.dialog_ref)
        self._cache_remember(
            self._input_entity_cache,
            keys=self._entity_cache_keys(resolved_chat, entity),
            value=peer,
        )
        self._remember_dialog_ref_input_entity(handle.dialog_ref, peer)
        slice_result = await self._read_dialog_slice_uncached(
            chat=resolved_chat,
            limit=limit,
            offset_id=offset_id,
            date_from=date_from,
            date_to=date_to,
            include_voice_transcription=include_voice_transcription,
            max_voice_transcriptions=max_voice_transcriptions,
            include_sender_name=include_sender_name,
            entity=entity,
            peer=peer,
        )
        return DialogReadResult(
            chat=handle,
            messages=slice_result.messages,
            message_count=len(slice_result.messages),
            has_more_before=slice_result.has_more_before,
            next_offset_id=slice_result.next_offset_id,
            range=DialogReadRange(date_from=date_from, date_to=date_to),
            data_source="live_telegram",
            voice_transcription_status=slice_result.voice_transcription_status,
            voice_transcription_count=slice_result.voice_transcription_count,
            omitted_voice_count=slice_result.omitted_voice_count,
            sender_resolution_count=slice_result.sender_resolution_count,
            truncated=slice_result.truncated,
            truncated_reason=slice_result.truncated_reason,
        )

    async def read_dialog_by_date(
        self,
        chat: str | int,
        date_from: str,
        date_to: str,
        total_limit: int = 20,
        offset_id: int = 0,
        include_voice_transcription: bool = False,
        max_voice_transcriptions: int | None = None,
        include_sender_name: bool = False,
    ) -> DialogReadResult:
        cache_key = self._make_result_cache_key(
            "dialog_read",
            "by_date",
            chat,
            date_from,
            date_to,
            total_limit,
            offset_id,
            include_voice_transcription,
            max_voice_transcriptions,
            include_sender_name,
        )
        cached = self._dialog_read_cache_get(cache_key)
        if cached is not None:
            return cached

        return await self._dedupe_read_call(
            (
                "read_dialog_by_date",
                chat,
                date_from,
                date_to,
                total_limit,
                offset_id,
                include_voice_transcription,
                max_voice_transcriptions,
                include_sender_name,
            ),
            lambda: self._read_dialog_by_date_cached(
                cache_key=cache_key,
                chat=chat,
                date_from=date_from,
                date_to=date_to,
                total_limit=total_limit,
                offset_id=offset_id,
                include_voice_transcription=include_voice_transcription,
                max_voice_transcriptions=max_voice_transcriptions,
                include_sender_name=include_sender_name,
            ),
        )

    async def _read_dialog_by_date_cached(
        self,
        *,
        cache_key: str,
        chat: str | int,
        date_from: str,
        date_to: str,
        total_limit: int = 20,
        offset_id: int = 0,
        include_voice_transcription: bool = False,
        max_voice_transcriptions: int | None = None,
        include_sender_name: bool = False,
    ) -> DialogReadResult:
        result = await self._read_dialog_by_date_uncached(
            chat=chat,
            date_from=date_from,
            date_to=date_to,
            total_limit=total_limit,
            offset_id=offset_id,
            include_voice_transcription=include_voice_transcription,
            max_voice_transcriptions=max_voice_transcriptions,
            include_sender_name=include_sender_name,
        )
        if result.voice_transcription_status not in {"failed", "partial", "pending"}:
            self._dialog_read_cache_set(cache_key, result)
        return result

    async def _read_dialog_by_date_uncached(
        self,
        chat: str | int,
        date_from: str,
        date_to: str,
        total_limit: int = 20,
        offset_id: int = 0,
        include_voice_transcription: bool = False,
        max_voice_transcriptions: int | None = None,
        include_sender_name: bool = False,
    ) -> DialogReadResult:
        started_at = time.perf_counter()
        result = await self._read_dialog_core(
            chat=chat,
            limit=total_limit,
            offset_id=offset_id,
            date_from=date_from,
            date_to=date_to,
            include_voice_transcription=include_voice_transcription,
            max_voice_transcriptions=max_voice_transcriptions,
            include_sender_name=include_sender_name,
        )
        self._emit_read_timing(
            "read_dialog_by_date",
            started_at,
            item_count=result.message_count,
            has_more_before=result.has_more_before,
            voice_transcription_status=result.voice_transcription_status,
            voice_transcription_count=result.voice_transcription_count,
            omitted_voice_count=result.omitted_voice_count,
            sender_resolution_count=result.sender_resolution_count,
        )
        return result

    async def read_today_dialog(
        self,
        chat: str | int,
        day: str | None = None,
        limit: int = 20,
        offset_id: int = 0,
        include_voice_transcription: bool = False,
        max_voice_transcriptions: int | None = None,
        include_sender_name: bool = False,
    ) -> DialogReadResult:
        target_day = day or date.today().isoformat()
        return await self.read_dialog_by_date(
            chat=chat,
            date_from=target_day,
            date_to=target_day,
            total_limit=limit,
            offset_id=offset_id,
            include_voice_transcription=include_voice_transcription,
            max_voice_transcriptions=max_voice_transcriptions,
            include_sender_name=include_sender_name,
        )

    async def read_recent_dialog(
        self,
        chat: str | int,
        limit: int = 20,
        offset_id: int = 0,
        include_voice_transcription: bool = False,
        max_voice_transcriptions: int | None = None,
        include_sender_name: bool = False,
    ) -> DialogReadResult:
        cache_key = self._make_result_cache_key(
            "dialog_read",
            "recent",
            chat,
            limit,
            offset_id,
            include_voice_transcription,
            max_voice_transcriptions,
            include_sender_name,
        )
        cached = self._dialog_read_cache_get(cache_key)
        if cached is not None:
            return cached

        return await self._dedupe_read_call(
            (
                "read_recent_dialog",
                chat,
                limit,
                offset_id,
                include_voice_transcription,
                max_voice_transcriptions,
                include_sender_name,
            ),
            lambda: self._read_recent_dialog_cached(
                cache_key=cache_key,
                chat=chat,
                limit=limit,
                offset_id=offset_id,
                include_voice_transcription=include_voice_transcription,
                max_voice_transcriptions=max_voice_transcriptions,
                include_sender_name=include_sender_name,
            ),
        )

    async def _read_recent_dialog_cached(
        self,
        *,
        cache_key: str,
        chat: str | int,
        limit: int = 20,
        offset_id: int = 0,
        include_voice_transcription: bool = False,
        max_voice_transcriptions: int | None = None,
        include_sender_name: bool = False,
    ) -> DialogReadResult:
        result = await self._read_recent_dialog_uncached(
            chat=chat,
            limit=limit,
            offset_id=offset_id,
            include_voice_transcription=include_voice_transcription,
            max_voice_transcriptions=max_voice_transcriptions,
            include_sender_name=include_sender_name,
        )
        if result.voice_transcription_status not in {"failed", "partial", "pending"}:
            self._dialog_read_cache_set(cache_key, result)
        return result

    async def _read_recent_dialog_uncached(
        self,
        chat: str | int,
        limit: int = 20,
        offset_id: int = 0,
        include_voice_transcription: bool = False,
        max_voice_transcriptions: int | None = None,
        include_sender_name: bool = False,
    ) -> DialogReadResult:
        started_at = time.perf_counter()
        result = await self._read_dialog_core(
            chat=chat,
            limit=limit,
            offset_id=offset_id,
            include_voice_transcription=include_voice_transcription,
            max_voice_transcriptions=max_voice_transcriptions,
            include_sender_name=include_sender_name,
        )
        self._emit_read_timing(
            "read_recent_dialog",
            started_at,
            item_count=result.message_count,
            has_more_before=result.has_more_before,
            voice_transcription_status=result.voice_transcription_status,
            voice_transcription_count=result.voice_transcription_count,
            omitted_voice_count=result.omitted_voice_count,
            sender_resolution_count=result.sender_resolution_count,
        )
        return result
