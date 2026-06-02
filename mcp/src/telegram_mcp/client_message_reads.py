"""Dialog and message read operations for TelegramWrapper."""

from __future__ import annotations

import time
from typing import Any

from .types import DialogSliceResult, MessageInfo, TranscriptionResult


class MessageReadMixin:
    """Live dialog read operations."""

    async def transcribe_voice(self, chat: str | int, message_id: int) -> TranscriptionResult:
        """Transcribe a voice/video message using Telegram's built-in transcription."""
        entity = await self._resolve_entity(chat)
        peer = await self._resolve_input_entity(chat)
        result = await self._transcribe_telegram_audio(
            entity=entity,
            peer=peer,
            message_id=message_id,
            label="transcribe_voice",
        )
        return TranscriptionResult(text=result.text, pending=result.pending)

    async def list_messages(
        self,
        chat: str | int,
        limit: int = 20,
        offset_id: int = 0,
        min_id: int = 0,
        max_id: int = 0,
        include_voice_transcription: bool = False,
        max_voice_transcriptions: int | None = None,
        include_sender_name: bool = True,
    ) -> list[MessageInfo]:
        return await self._dedupe_read_call(
            (
                "list_messages",
                chat,
                limit,
                offset_id,
                min_id,
                max_id,
                include_voice_transcription,
                max_voice_transcriptions,
                include_sender_name,
            ),
            lambda: self._list_messages_uncached(
                chat=chat,
                limit=limit,
                offset_id=offset_id,
                min_id=min_id,
                max_id=max_id,
                include_voice_transcription=include_voice_transcription,
                max_voice_transcriptions=max_voice_transcriptions,
                include_sender_name=include_sender_name,
            ),
        )

    async def _list_messages_uncached(
        self,
        chat: str | int,
        limit: int = 20,
        offset_id: int = 0,
        min_id: int = 0,
        max_id: int = 0,
        include_voice_transcription: bool = False,
        max_voice_transcriptions: int | None = None,
        include_sender_name: bool = True,
    ) -> list[MessageInfo]:
        started_at = time.perf_counter()
        self._validate_message_window(
            limit=limit,
            offset_id=offset_id,
            min_id=min_id,
            max_id=max_id,
        )
        entity = await self._resolve_entity(chat)
        peer = await self._resolve_input_entity(chat)
        result = await self._collect_messages(
            label="list_messages",
            entity=entity,
            peer=peer,
            limit=limit,
            offset_id=offset_id,
            min_id=min_id,
            max_id=max_id,
            include_voice_transcription=include_voice_transcription,
            max_voice_transcriptions=max_voice_transcriptions,
            include_sender_name=include_sender_name,
        )
        self._emit_read_timing(
            "list_messages",
            started_at,
            item_count=len(result.messages),
            has_more_before=result.has_more_before,
            voice_transcription_status=result.stats.voice_transcription_status,
            voice_transcription_count=result.stats.voice_transcription_count,
            omitted_voice_count=result.stats.omitted_voice_count,
            sender_resolution_count=result.stats.sender_resolution_count,
            truncated=result.truncated,
            truncated_reason=result.truncated_reason,
        )
        return result.messages

    async def read_dialog_slice(
        self,
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
        return await self._dedupe_read_call(
            (
                "read_dialog_slice",
                chat,
                limit,
                offset_id,
                min_id,
                max_id,
                include_voice_transcription,
                max_voice_transcriptions,
                include_sender_name,
                date_from,
                date_to,
            ),
            lambda: self._read_dialog_slice_uncached(
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
            ),
        )

    async def _read_dialog_slice_uncached(
        self,
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
        entity: Any | None = None,
        peer: Any | None = None,
    ) -> DialogSliceResult:
        started_at = time.perf_counter()
        self._validate_message_window(
            limit=limit,
            offset_id=offset_id,
            min_id=min_id,
            max_id=max_id,
        )
        if entity is None:
            entity = await self._resolve_entity(chat)
        if peer is None:
            peer = await self._resolve_input_entity(chat)
        lower_bound, upper_bound_exclusive = self._build_day_bounds(
            date_from=date_from,
            date_to=date_to,
        )
        result = await self._collect_messages(
            label="read_dialog_slice",
            entity=entity,
            peer=peer,
            limit=limit,
            offset_id=offset_id,
            min_id=min_id,
            max_id=max_id,
            include_voice_transcription=include_voice_transcription,
            max_voice_transcriptions=max_voice_transcriptions,
            include_sender_name=include_sender_name,
            lower_bound=lower_bound,
            upper_bound_exclusive=upper_bound_exclusive,
        )
        self._emit_read_timing(
            "read_dialog_slice",
            started_at,
            item_count=len(result.messages),
            has_more_before=result.has_more_before,
            voice_transcription_status=result.stats.voice_transcription_status,
            voice_transcription_count=result.stats.voice_transcription_count,
            omitted_voice_count=result.stats.omitted_voice_count,
            sender_resolution_count=result.stats.sender_resolution_count,
            truncated=result.truncated,
            truncated_reason=result.truncated_reason,
        )
        return DialogSliceResult(
            chat=self._chat_info_from_entity(entity),
            messages=result.messages,
            has_more_before=result.has_more_before,
            next_offset_id=(
                result.messages[-1].id
                if result.has_more_before and result.messages
                else None
            ),
            voice_transcription_status=result.stats.voice_transcription_status,
            voice_transcription_count=result.stats.voice_transcription_count,
            omitted_voice_count=result.stats.omitted_voice_count,
            sender_resolution_count=result.stats.sender_resolution_count,
            truncated=result.truncated,
            truncated_reason=result.truncated_reason,
        )
