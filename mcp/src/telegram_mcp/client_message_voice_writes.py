"""Voice message write helpers for TelegramWrapper."""

from __future__ import annotations

import time

from .file_path_policy import validate_outbound_media_path
from .types import MessageInfo


class MessageVoiceWriteMixin:
    """Media-lane voice send operation."""

    async def send_voice(
        self, chat: str | int, file_path: str
    ) -> MessageInfo:
        safe_file_path = validate_outbound_media_path(file_path)
        entity = await self._resolve_entity(chat)
        started_at = time.perf_counter()
        self._append_write_audit_event(
            "send_voice",
            "started",
            started_at,
            lane="media",
        )
        try:
            msg = await self._run_media(
                "send_voice",
                lambda: self.client.send_file(
                    entity,
                    safe_file_path,
                    voice_note=True,
                ),
            )
        except BaseException as exc:
            self._append_write_audit_event(
                "send_voice",
                "failed",
                started_at,
                lane="media",
                error=exc,
            )
            raise
        self._append_write_audit_event(
            "send_voice",
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
            media_type="voice",
        )
