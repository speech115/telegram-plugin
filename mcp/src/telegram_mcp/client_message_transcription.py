"""Telegram audio transcription helpers for messages."""

from __future__ import annotations

from typing import Any

from telethon.tl.functions.messages import TranscribeAudioRequest

from .client_message_models import _TranscriptionOutcome


class MessageTranscriptionMixin:
    """Shared Telegram TranscribeAudioRequest helpers."""

    @staticmethod
    def _transcript_chat_id(entity: Any) -> int | None:
        for attr in ("id", "channel_id", "chat_id", "user_id"):
            value = getattr(entity, attr, None)
            if isinstance(value, int):
                return value
        return None

    async def _transcribe_telegram_audio(
        self,
        *,
        entity: Any,
        peer: Any,
        message_id: int,
        label: str,
    ) -> _TranscriptionOutcome:
        chat_id = self._transcript_chat_id(entity)
        if chat_id is not None:
            cached = self._transcript_cache_get(chat_id, message_id)
            if cached is not None:
                return _TranscriptionOutcome(text=cached, pending=False)

        async def request_transcription() -> _TranscriptionOutcome:
            if chat_id is not None:
                cached = self._transcript_cache_get(chat_id, message_id)
                if cached is not None:
                    return _TranscriptionOutcome(text=cached, pending=False)

            result = await self._run_transcribe(
                label,
                lambda: self.client(
                    TranscribeAudioRequest(peer=peer, msg_id=message_id)
                ),
            )
            pending = bool(getattr(result, "pending", False))
            text = getattr(result, "text", None)
            if not pending and chat_id is not None:
                if text is None:
                    text = ""
                self._transcript_cache_set(chat_id, message_id, text)
            return _TranscriptionOutcome(text=text, pending=pending)

        if chat_id is None:
            return await request_transcription()
        return await self._dedupe_read_call(
            ("transcribe_audio", chat_id, message_id),
            request_transcription,
        )
