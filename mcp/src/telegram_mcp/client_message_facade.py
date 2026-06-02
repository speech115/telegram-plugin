"""Task-shaped dialog facade helpers for TelegramWrapper."""

from __future__ import annotations

import hashlib
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path

from .errors import ToolContractError
from .file_path_policy import validate_outbound_media_path
from .types import (
    DialogContextResult,
    DialogFileSendPreparation,
    DialogReplyPreparation,
    DialogSendPreparation,
    MessageInfo,
)


class MessageFacadeMixin:
    """Agent-facing dialog facade and preview helpers."""

    _send_confirmation_ttl_seconds = 300

    def _text_hash(self, text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    async def _confirmation_account_id(self) -> int:
        return (await self.get_me()).id

    def _send_confirmation_payload(
        self,
        *,
        account_id: int,
        send_tool: str,
        chat: str | int,
        text: str,
        parse_mode: str | None,
        message_id: int | None = None,
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            "account_id": account_id,
            "send_tool": send_tool,
            "chat": chat,
            "text_hash": self._text_hash(text),
            "parse_mode": parse_mode,
        }
        if message_id is not None:
            payload["message_id"] = message_id
        return payload

    def _mint_send_confirmation(self, payload: dict[str, object]) -> tuple[str, datetime]:
        token = secrets.token_urlsafe(24)
        expires_at = time.time() + self._send_confirmation_ttl_seconds
        self._dialog_send_confirmations[token] = (expires_at, payload)
        return token, datetime.fromtimestamp(expires_at, tz=timezone.utc)

    def _consume_send_confirmation(self, token: str | None, expected: dict[str, object]) -> None:
        if not token:
            raise ToolContractError(
                "missing_confirmation_token",
                "send/reply requires a fresh preview confirmation token",
            )
        stored = self._dialog_send_confirmations.pop(token, None)
        if stored is None:
            raise ToolContractError("invalid_confirmation_token", "confirmation token is unknown or already used")
        expires_at, actual = stored
        if time.time() > expires_at:
            raise ToolContractError("expired_confirmation_token", "confirmation token has expired")
        if actual != expected:
            raise ToolContractError(
                "confirmation_payload_mismatch",
                "send/reply arguments do not match the preview confirmation",
            )

    async def collect_dialog_context(
        self,
        chat: str | int,
        *,
        mode: str = "fast",
        recent_limit: int = 50,
        date_from: str | None = None,
        date_to: str | None = None,
        offset_id: int = 0,
        include_pinned: bool = False,
        pinned_limit: int = 5,
        include_voice_transcription: bool | None = None,
        max_voice_transcriptions: int | None = None,
    ) -> DialogContextResult:
        normalized_mode = mode.strip().lower()
        if normalized_mode not in {"fast", "full"}:
            raise ToolContractError(
                "invalid_context_mode",
                "mode must be 'fast' or 'full'",
            )

        include_sender_name = normalized_mode == "full"
        if include_voice_transcription is None:
            include_voice = normalized_mode == "full"
        else:
            include_voice = include_voice_transcription

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
                total_limit=recent_limit,
                offset_id=offset_id,
                include_voice_transcription=include_voice,
                max_voice_transcriptions=max_voice_transcriptions,
                include_sender_name=include_sender_name,
            )
        else:
            read_result = await self.read_recent_dialog(
                chat=chat,
                limit=recent_limit,
                offset_id=offset_id,
                include_voice_transcription=include_voice,
                max_voice_transcriptions=max_voice_transcriptions,
                include_sender_name=include_sender_name,
            )

        pinned_messages: list[MessageInfo] = []
        if include_pinned and pinned_limit > 0:
            pinned_result = await self._get_pinned_messages_with_caps(
                chat=chat,
                limit=pinned_limit,
                include_sender_name=include_sender_name,
            )
            pinned_messages = pinned_result.messages

        evidence_message_ids = [message.id for message in read_result.messages]
        media_message_ids = [
            message.id for message in read_result.messages if message.has_media
        ]
        return DialogContextResult(
            chat=read_result.chat,
            messages=read_result.messages,
            message_count=read_result.message_count,
            pinned_messages=pinned_messages,
            pinned_count=len(pinned_messages),
            evidence_message_ids=evidence_message_ids,
            media_message_ids=media_message_ids,
            has_more_before=read_result.has_more_before,
            next_offset_id=read_result.next_offset_id,
            range=read_result.range,
            data_source=read_result.data_source,
            collection_mode=normalized_mode,
            include_voice_transcription=include_voice,
            voice_transcription_status=read_result.voice_transcription_status,
            voice_transcription_count=read_result.voice_transcription_count,
            omitted_voice_count=read_result.omitted_voice_count,
            sender_resolution_count=read_result.sender_resolution_count,
            truncated=read_result.truncated,
            truncated_reason=read_result.truncated_reason,
        )

    async def prepare_dialog_reply(
        self,
        chat: str | int,
        goal: str,
        *,
        reply_to_message_id: int | None = None,
        context_limit: int = 20,
        mode: str = "fast",
        draft_text: str | None = None,
    ) -> DialogReplyPreparation:
        context = await self.collect_dialog_context(
            chat=chat,
            mode=mode,
            recent_limit=context_limit,
            include_pinned=False,
        )
        draft = draft_text or ""
        send_tool = "telegram_confirmed_send"
        send_args_preview: dict[str, object] = {
            "chat": context.chat.dialog_ref,
            "text": draft,
        }
        confirmation_token: str | None = None
        confirmation_expires_at: datetime | None = None
        if draft:
            account_id = await self._confirmation_account_id()
            storage_payload = self._send_confirmation_payload(
                account_id=account_id,
                send_tool="reply_in_dialog" if reply_to_message_id is not None else "send_dialog_message",
                chat=context.chat.dialog_ref,
                text=draft,
                parse_mode="md",
                message_id=reply_to_message_id,
            )
            confirmation_token, confirmation_expires_at = self._mint_send_confirmation(storage_payload)
            send_args_preview["confirmation_token"] = confirmation_token
            if reply_to_message_id is not None:
                send_args_preview["message_id"] = reply_to_message_id

        warnings = [
            "preview_only: this tool never sends messages; use telegram_confirmed_send with the preview token after review."
        ]
        if context.truncated or context.has_more_before:
            warnings.append(
                "context_incomplete: fetch the next page before relying on this as complete context."
            )

        return DialogReplyPreparation(
            chat=context.chat,
            goal=goal,
            context=context,
            evidence_message_ids=context.evidence_message_ids,
            reply_target_message_id=reply_to_message_id,
            draft_text=draft_text,
            preview_only=True,
            send_tool=send_tool,
            send_args_preview=send_args_preview,
            warnings=warnings,
            confirmation_token=confirmation_token,
            confirmation_expires_at=confirmation_expires_at,
        )

    async def prepare_send_message(
        self,
        chat: str | int,
        text: str,
        parse_mode: str = "md",
    ) -> DialogSendPreparation:
        handle = await self.resolve_dialog(chat)
        account_id = await self._confirmation_account_id()
        storage_payload = self._send_confirmation_payload(
            account_id=account_id,
            send_tool="send_dialog_message",
            chat=handle.dialog_ref,
            text=text,
            parse_mode=parse_mode or None,
        )
        confirmation_token, confirmation_expires_at = self._mint_send_confirmation(storage_payload)
        return DialogSendPreparation(
            chat=handle,
            text=text,
            parse_mode=parse_mode or None,
            preview_only=True,
            send_tool="telegram_confirmed_send",
            send_args_preview={
                "chat": handle.dialog_ref,
                "text": text,
                "parse_mode": parse_mode or None,
                "confirmation_token": confirmation_token,
            },
            confirmation_token=confirmation_token,
            confirmation_expires_at=confirmation_expires_at,
        )

    async def prepare_reply_message(
        self,
        chat: str | int,
        message_id: int,
        text: str,
        parse_mode: str = "md",
    ) -> DialogSendPreparation:
        self._validate_non_negative("message_id", message_id)
        handle = await self.resolve_dialog(chat)
        account_id = await self._confirmation_account_id()
        storage_payload = self._send_confirmation_payload(
            account_id=account_id,
            send_tool="reply_in_dialog",
            chat=handle.dialog_ref,
            text=text,
            parse_mode=parse_mode or None,
            message_id=message_id,
        )
        confirmation_token, confirmation_expires_at = self._mint_send_confirmation(storage_payload)
        return DialogSendPreparation(
            chat=handle,
            text=text,
            parse_mode=parse_mode or None,
            reply_target_message_id=message_id,
            preview_only=True,
            send_tool="telegram_confirmed_send",
            send_args_preview={
                "chat": handle.dialog_ref,
                "message_id": message_id,
                "text": text,
                "parse_mode": parse_mode or None,
                "confirmation_token": confirmation_token,
            },
            confirmation_token=confirmation_token,
            confirmation_expires_at=confirmation_expires_at,
        )

    async def prepare_send_file(
        self,
        chat: str | int,
        file_path: str,
        caption: str = "",
        parse_mode: str = "md",
    ) -> DialogFileSendPreparation:
        validated_path = validate_outbound_media_path(file_path)
        handle = await self.resolve_dialog(chat)
        media_path = Path(validated_path)
        preview_token = secrets.token_urlsafe(12)[:16]
        warnings = [
            "preview_only: this tool never sends files; it validates and prepares send arguments only."
        ]
        return DialogFileSendPreparation(
            chat=handle,
            file_path=validated_path,
            file_name=media_path.name,
            caption=caption,
            parse_mode=parse_mode or None,
            preview_only=True,
            send_tool="send_file",
            send_args_preview={
                "chat": handle.dialog_ref,
                "file_path": validated_path,
                "caption": caption,
                "parse_mode": parse_mode or None,
            },
            preview_token=preview_token,
            warnings=warnings,
        )

    async def send_dialog_message(
        self,
        chat: str | int,
        text: str,
        parse_mode: str = "md",
        confirmation_token: str | None = None,
    ) -> MessageInfo:
        account_id = await self._confirmation_account_id()
        self._consume_send_confirmation(
            confirmation_token,
            self._send_confirmation_payload(
                account_id=account_id,
                send_tool="send_dialog_message",
                chat=chat,
                text=text,
                parse_mode=parse_mode or None,
            ),
        )
        return await self.send_message(
            chat=self._coerce_dialog_query(chat),
            text=text,
            parse_mode=parse_mode,
        )

    async def reply_in_dialog(
        self,
        chat: str | int,
        message_id: int,
        text: str,
        parse_mode: str = "md",
        confirmation_token: str | None = None,
    ) -> MessageInfo:
        account_id = await self._confirmation_account_id()
        self._consume_send_confirmation(
            confirmation_token,
            self._send_confirmation_payload(
                account_id=account_id,
                send_tool="reply_in_dialog",
                chat=chat,
                text=text,
                parse_mode=parse_mode or None,
                message_id=message_id,
            ),
        )
        return await self.reply_to_message(
            chat=self._coerce_dialog_query(chat),
            message_id=message_id,
            text=text,
            parse_mode=parse_mode,
        )
