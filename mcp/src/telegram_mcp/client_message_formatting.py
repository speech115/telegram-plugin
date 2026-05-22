"""Message validation and formatting helpers."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

from .errors import ToolContractError
from .types import MessageInfo
from .utils import get_media_duration_seconds, get_media_type, get_sender_name


class MessageFormattingMixin:
    """Shared validation, date, sender, and MessageInfo formatting helpers."""

    def _validate_message_window(
        self,
        *,
        limit: int,
        offset_id: int = 0,
        min_id: int = 0,
        max_id: int = 0,
    ) -> None:
        self._validate_non_negative("limit", limit)
        self._validate_non_negative("offset_id", offset_id)
        self._validate_non_negative("min_id", min_id)
        self._validate_non_negative("max_id", max_id)
        if min_id and max_id and min_id > max_id:
            raise ToolContractError(
                "invalid_pagination",
                "min_id must be less than or equal to max_id",
            )

    def _coerce_dialog_query(self, chat: str | int) -> str | int:
        if not isinstance(chat, str):
            return chat

        normalized = chat.strip()
        prefix = "tg://dialog/"
        if not normalized.startswith(prefix):
            return chat

        try:
            peer_type, peer_id = normalized.removeprefix(prefix).split("/", 1)
        except ValueError as exc:
            raise ToolContractError(
                "dialog_not_found",
                "dialog_ref must be tg://dialog/<type>/<id>",
            ) from exc

        if not peer_type or not peer_id:
            raise ToolContractError(
                "dialog_not_found",
                "dialog_ref must be tg://dialog/<type>/<id>",
            )
        return normalized

    def _build_day_bounds(
        self,
        *,
        date_from: str | None,
        date_to: str | None,
    ) -> tuple[datetime | None, datetime | None]:
        def parse_day(raw_value: str | None, label: str) -> datetime | None:
            if raw_value is None:
                return None
            normalized = raw_value.strip()
            if not normalized:
                return None
            try:
                parsed_day = date.fromisoformat(normalized)
            except ValueError as exc:
                raise ToolContractError(
                    "invalid_date_range",
                    f"{label} must be YYYY-MM-DD",
                ) from exc
            return datetime(parsed_day.year, parsed_day.month, parsed_day.day, tzinfo=UTC)

        lower_bound = parse_day(date_from, "date_from")
        upper_bound = parse_day(date_to, "date_to")
        upper_bound_exclusive = (
            upper_bound + timedelta(days=1)
            if upper_bound is not None
            else None
        )
        if (
            lower_bound is not None
            and upper_bound_exclusive is not None
            and lower_bound >= upper_bound_exclusive
        ):
            raise ToolContractError(
                "invalid_date_range",
                "date_from must be less than or equal to date_to",
            )
        return lower_bound, upper_bound_exclusive

    def _normalize_message_datetime(self, value: datetime) -> datetime:
        return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)

    async def _resolve_message_sender(
        self,
        msg: Any,
        *,
        sender_cache: dict[int, Any | None] | None = None,
    ) -> Any | None:
        sender = getattr(msg, "sender", None)
        sender_id = getattr(msg, "sender_id", None)
        if sender is not None or sender_id is None:
            return sender
        if sender_cache is not None and sender_id in sender_cache:
            return sender_cache[sender_id]
        sender = await self._run_enrich(
            "resolve_message_sender",
            msg.get_sender,
        )
        if sender_cache is not None:
            sender_cache[sender_id] = sender
        return sender

    def _message_to_info(
        self,
        msg: Any,
        *,
        default_chat_id: int,
        sender: Any | None = None,
        voice_transcription: str | None = None,
        reply_to_msg_id: int | None = None,
        is_outgoing: bool | None = None,
        has_media: bool | None = None,
        media_type: str | None = None,
        voice_transcription_status: str | None = None,
        voice_transcription_error: str | None = None,
    ) -> MessageInfo:
        resolved_reply_to = reply_to_msg_id
        if resolved_reply_to is None:
            reply_to = getattr(msg, "reply_to", None)
            resolved_reply_to = (
                getattr(reply_to, "reply_to_msg_id", None)
                if reply_to is not None
                else None
            )

        document = getattr(msg, "document", None)
        mime_type = getattr(document, "mime_type", None) if document is not None else None
        file_size = getattr(document, "size", None) if document is not None else None

        return MessageInfo(
            id=msg.id,
            chat_id=getattr(msg, "chat_id", None) or default_chat_id,
            sender_id=getattr(msg, "sender_id", None),
            sender_name=get_sender_name(sender),
            date=msg.date,
            text=getattr(msg, "text", "") or "",
            reply_to_msg_id=resolved_reply_to,
            is_outgoing=(
                getattr(msg, "out", False) or False
                if is_outgoing is None
                else is_outgoing
            ),
            has_media=(
                getattr(msg, "media", None) is not None
                if has_media is None
                else has_media
            ),
            media_type=get_media_type(msg) if media_type is None else media_type,
            mime_type=mime_type,
            file_size=file_size,
            duration_seconds=get_media_duration_seconds(msg),
            views=getattr(msg, "views", None),
            forwards=getattr(msg, "forwards", None),
            edit_date=getattr(msg, "edit_date", None),
            voice_transcription=voice_transcription,
            voice_transcription_status=voice_transcription_status,
            voice_transcription_error=voice_transcription_error,
        )
