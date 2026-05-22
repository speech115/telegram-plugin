"""Shared message collection helpers for TelegramWrapper."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .client_message_caps import MessageCapsMixin
from .client_message_formatting import MessageFormattingMixin
from .client_message_models import (
    _FetchedMessageRecord,
    _MessageCollectionResult,
    _MessageCollectionStats,
    _TranscriptionOutcome,
)
from .client_message_transcription import MessageTranscriptionMixin
from .errors import ToolContractError
from .types import MessageInfo
from .utils import get_media_type


class MessageCommonMixin(
    MessageFormattingMixin,
    MessageTranscriptionMixin,
    MessageCapsMixin,
):
    """Shared collection helpers for message read, search, and pinned operations."""

    async def _fetch_message_records(
        self,
        *,
        entity: Any,
        limit: int,
        offset_id: int,
        min_id: int,
        max_id: int,
        lower_bound: datetime | None = None,
        upper_bound_exclusive: datetime | None = None,
    ) -> tuple[list[_FetchedMessageRecord], bool]:
        self._validate_message_window(
            limit=limit,
            offset_id=offset_id,
            min_id=min_id,
            max_id=max_id,
        )
        if limit <= 0:
            return [], False

        records = []
        iter_kwargs: dict[str, Any] = {
            "limit": limit + 1,
            "offset_id": offset_id,
            "min_id": min_id,
            "max_id": max_id,
        }
        if upper_bound_exclusive is not None:
            iter_kwargs["offset_date"] = upper_bound_exclusive

        async for msg in self.client.iter_messages(entity, **iter_kwargs):
            message_timestamp = self._normalize_message_datetime(msg.date)
            if (
                upper_bound_exclusive is not None
                and message_timestamp >= upper_bound_exclusive
            ):
                continue
            if lower_bound is not None and message_timestamp < lower_bound:
                break
            if len(records) >= limit:
                return records, True
            records.append(
                _FetchedMessageRecord(
                    message=msg,
                    media_type=get_media_type(msg),
                )
            )
        return records, False

    async def _enrich_message_records(
        self,
        *,
        entity: Any,
        peer: Any,
        records: list[_FetchedMessageRecord],
        include_voice_transcription: bool,
        max_voice_transcriptions: int | None,
        include_sender_name: bool,
        stats: _MessageCollectionStats,
    ) -> list[MessageInfo]:
        voice_budget = max_voice_transcriptions
        sender_cache: dict[int, Any | None] = {}
        messages = []

        for record in records:
            msg = record.message
            sender_id = getattr(msg, "sender_id", None)
            needs_sender_fetch = (
                include_sender_name
                and
                getattr(msg, "sender", None) is None
                and sender_id is not None
                and sender_id not in sender_cache
            )
            sender = None
            if include_sender_name:
                sender = await self._resolve_message_sender(
                    msg,
                    sender_cache=sender_cache,
                )
            if needs_sender_fetch:
                stats.sender_resolution_count += 1
            media_type = record.media_type

            voice_transcription = None
            voice_transcription_status = None
            voice_transcription_error = None
            should_transcribe = (
                include_voice_transcription
                and media_type in {"voice", "video_note"}
            )
            if should_transcribe:
                if (
                    voice_budget is not None
                    and stats.voice_transcription_count >= voice_budget
                ):
                    stats.omitted_voice_count += 1
                    voice_transcription_status = "omitted"
                else:
                    try:
                        result = await self._transcribe_telegram_audio(
                            entity=entity,
                            peer=peer,
                            message_id=msg.id,
                            label="transcribe_voice_inline",
                        )
                        stats.voice_transcription_count += 1
                        if not result.pending:
                            voice_transcription = result.text
                            voice_transcription_status = "complete"
                        else:
                            stats.pending_voice_count += 1
                            voice_transcription_status = "pending"
                    except ToolContractError as exc:
                        stats.failed_voice_count += 1
                        voice_transcription_status = (
                            exc.code
                            if exc.code in {"operation_timeout", "rate_limited"}
                            else "failed"
                        )
                        voice_transcription_error = str(exc)
                    except Exception:
                        stats.failed_voice_count += 1
                        voice_transcription_status = "failed"
                        voice_transcription_error = "TranscribeAudioRequest failed"

            messages.append(
                self._message_to_info(
                    msg,
                    default_chat_id=getattr(entity, "id", 0),
                    sender=sender,
                    voice_transcription=voice_transcription,
                    voice_transcription_status=voice_transcription_status,
                    voice_transcription_error=voice_transcription_error,
                    media_type=media_type,
                )
            )
        return messages

    async def _collect_messages(
        self,
        *,
        label: str,
        entity: Any,
        peer: Any,
        limit: int,
        offset_id: int,
        min_id: int,
        max_id: int,
        include_voice_transcription: bool,
        max_voice_transcriptions: int | None = None,
        include_sender_name: bool = True,
        lower_bound: datetime | None = None,
        upper_bound_exclusive: datetime | None = None,
    ) -> _MessageCollectionResult:
        self._validate_message_window(
            limit=limit,
            offset_id=offset_id,
            min_id=min_id,
            max_id=max_id,
        )
        if max_voice_transcriptions is not None:
            self._validate_non_negative(
                "max_voice_transcriptions",
                max_voice_transcriptions,
            )
        voice_budget = max_voice_transcriptions
        if include_voice_transcription and voice_budget is None:
            voice_budget = self.settings.default_voice_transcription_budget
            self._validate_non_negative(
                "default_voice_transcription_budget",
                voice_budget,
            )

        stats = _MessageCollectionStats()
        if limit <= 0:
            stats.finish(include_voice_transcription=include_voice_transcription)
            return _MessageCollectionResult(
                messages=[],
                has_more_before=False,
                stats=stats,
            )

        fetch_limit, request_was_capped = self._bounded_read_limit(limit)

        records, has_more_before = await self._run_read(
            label,
            lambda: self._fetch_message_records(
                entity=entity,
                limit=fetch_limit,
                offset_id=offset_id,
                min_id=min_id,
                max_id=max_id,
                lower_bound=lower_bound,
                upper_bound_exclusive=upper_bound_exclusive,
            ),
        )
        messages = await self._enrich_message_records(
            entity=entity,
            peer=peer,
            records=records,
            include_voice_transcription=include_voice_transcription,
            max_voice_transcriptions=voice_budget,
            include_sender_name=include_sender_name,
            stats=stats,
        )
        stats.finish(include_voice_transcription=include_voice_transcription)
        initial_reasons = (
            ["message_limit"] if request_was_capped and has_more_before else []
        )
        capped = self._apply_message_caps(messages, initial_reasons=initial_reasons)
        return _MessageCollectionResult(
            messages=capped.messages,
            has_more_before=has_more_before or capped.truncated,
            stats=stats,
            truncated=capped.truncated,
            truncated_reason=capped.truncated_reason,
        )
