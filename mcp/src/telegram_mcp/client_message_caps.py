"""Message read limit and truncation helpers."""

from __future__ import annotations

from dataclasses import dataclass

from .types import MessageInfo


@dataclass(frozen=True)
class MessageCapResult:
    messages: list[MessageInfo]
    truncated: bool = False
    truncated_reason: str | None = None
    sender_resolution_count: int = 0


class MessageCapsMixin:
    """Shared policy for bounded message payloads."""

    def _positive_int_setting(self, name: str, default: int) -> int:
        try:
            value = int(getattr(self.settings, name, default))
        except (TypeError, ValueError):
            value = default
        return max(1, value)

    def _read_max_messages(self) -> int:
        return self._positive_int_setting("read_max_messages", 100)

    def _bounded_read_limit(self, limit: int) -> tuple[int, bool]:
        max_messages = self._read_max_messages()
        return min(limit, max_messages), limit > max_messages

    @staticmethod
    def _join_truncated_reasons(reasons: list[str]) -> str | None:
        if not reasons:
            return None
        return ",".join(dict.fromkeys(reasons))

    @staticmethod
    def _truncate_text(value: str, max_chars: int) -> str:
        if max_chars <= 0:
            return ""
        if len(value) <= max_chars:
            return value
        if max_chars <= 3:
            return value[:max_chars]
        return value[: max_chars - 3] + "..."

    def _truncate_message_payload(
        self,
        message: MessageInfo,
        remaining_chars: int,
    ) -> MessageInfo | None:
        if remaining_chars <= 0:
            return None

        text = message.text or ""
        voice_transcription = message.voice_transcription
        updates: dict[str, str | None] = {}

        if len(text) >= remaining_chars:
            updates["text"] = self._truncate_text(text, remaining_chars)
            updates["voice_transcription"] = None
        elif voice_transcription:
            remaining_after_text = remaining_chars - len(text)
            updates["voice_transcription"] = self._truncate_text(
                voice_transcription,
                remaining_after_text,
            )

        return message.model_copy(update=updates) if updates else message

    def _apply_message_caps(
        self,
        messages: list[MessageInfo],
        *,
        initial_reasons: list[str] | None = None,
        sender_resolution_count: int = 0,
    ) -> MessageCapResult:
        reasons = list(initial_reasons or [])
        max_messages = self._read_max_messages()
        max_chars = self._positive_int_setting("read_max_chars", 40000)
        max_media_items = self._positive_int_setting("read_max_media_items", 25)

        capped_messages: list[MessageInfo] = []
        used_chars = 0
        used_media_items = 0

        for message in messages:
            if len(capped_messages) >= max_messages:
                reasons.append("message_limit")
                break

            if message.has_media:
                if used_media_items >= max_media_items:
                    reasons.append("media_limit")
                    break
                used_media_items += 1

            message_chars = len(message.text or "") + len(
                message.voice_transcription or ""
            )
            remaining_chars = max_chars - used_chars
            if message_chars > remaining_chars:
                truncated_message = self._truncate_message_payload(
                    message,
                    remaining_chars,
                )
                if truncated_message is not None:
                    capped_messages.append(truncated_message)
                reasons.append("char_limit")
                break

            capped_messages.append(message)
            used_chars += message_chars

        return MessageCapResult(
            messages=capped_messages,
            truncated=bool(reasons),
            truncated_reason=self._join_truncated_reasons(reasons),
            sender_resolution_count=sender_resolution_count,
        )
