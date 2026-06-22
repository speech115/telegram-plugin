"""Task-shaped dialog facade helpers for TelegramWrapper."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from .errors import ToolContractError
from .types import (
    DialogContextResult,
    DialogReplyPreparation,
    DialogSendPreparation,
    MessageInfo,
)


class MessageFacadeMixin:
    """Agent-facing dialog facade and preview helpers."""

    def _write_approval_required(self) -> bool:
        return bool(getattr(self.settings, "write_approval_required", True))

    def _approval_url(self, token: str) -> str:
        host = getattr(self.settings, "approval_host", "127.0.0.1")
        port = int(getattr(self.settings, "approval_port", 8798))
        return f"http://{host}:{port}/telegram/approve?token={token}"

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

    def _mint_send_confirmation(
        self,
        payload: dict[str, object],
        *,
        preview_text: str,
    ) -> tuple[str, str, datetime, str | None]:
        preview_id, token, expires_at = self._send_confirmation_store.mint(
            payload,
            preview_text=preview_text,
        )
        approval_url = self._approval_url(token) if self._write_approval_required() else None
        return preview_id, token, expires_at, approval_url

    def _consume_send_confirmation(
        self,
        key: str | None,
        expected: dict[str, object] | None,
        *,
        preview_id_only: bool = False,
    ) -> dict[str, object]:
        record = self._send_confirmation_store.consume(
            key,
            expected,
            approval_required=self._write_approval_required(),
            preview_id_only=preview_id_only,
        )
        return dict(record.payload)

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
            result_cache_hit=read_result.result_cache_hit,
            result_cache_age_seconds=read_result.result_cache_age_seconds,
            result_cache_ttl_seconds=read_result.result_cache_ttl_seconds,
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
        preview_id: str | None = None
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
            preview_id, confirmation_token, confirmation_expires_at, approval_url = self._mint_send_confirmation(
                storage_payload,
                preview_text=draft,
            )
            send_args_preview["confirmation_token"] = confirmation_token
            if reply_to_message_id is not None:
                send_args_preview["message_id"] = reply_to_message_id
        else:
            approval_url = None

        warnings = [
            "preview_only: this tool never sends messages; use telegram_confirmed_send with the preview token after review."
        ]
        if approval_url:
            warnings.append(f"human_approval_required: open {approval_url} and click Approve before sending.")
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
            preview_id=preview_id,
            human_approval_url=approval_url if draft else None,
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
        preview_id, confirmation_token, confirmation_expires_at, approval_url = self._mint_send_confirmation(
            storage_payload,
            preview_text=text,
        )
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
            preview_id=preview_id,
            human_approval_url=approval_url,
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
        preview_id, confirmation_token, confirmation_expires_at, approval_url = self._mint_send_confirmation(
            storage_payload,
            preview_text=text,
        )
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
            preview_id=preview_id,
            human_approval_url=approval_url,
        )

    async def _commit_confirmed_send(
        self,
        *,
        preview_id: str | None,
        confirmation_token: str | None,
        chat: str | int | None,
        text: str | None,
        parse_mode: str | None,
        message_id: int | None,
    ) -> MessageInfo:
        if preview_id:
            record = self._send_confirmation_store.consume(
                preview_id,
                None,
                approval_required=self._write_approval_required(),
                preview_id_only=True,
            )
            payload = record.payload
            resolved_chat = payload["chat"]
            resolved_text = record.preview_text
            resolved_parse = str(payload.get("parse_mode") or "md")
            resolved_message_id = payload.get("message_id")
            if resolved_message_id is not None:
                return await self.reply_in_dialog(
                    chat=resolved_chat,
                    message_id=int(resolved_message_id),
                    text=resolved_text,
                    parse_mode=resolved_parse,
                    confirmation_token=None,
                    _skip_confirmation=True,
                )
            return await self.send_dialog_message(
                chat=resolved_chat,
                text=resolved_text,
                parse_mode=resolved_parse,
                confirmation_token=None,
                _skip_confirmation=True,
            )

        if chat is None or text is None:
            raise ToolContractError("missing_send_target", "chat and text are required without preview_id")
        if self._write_approval_required() or confirmation_token:
            account_id = await self._confirmation_account_id()
            self._consume_send_confirmation(
                confirmation_token,
                self._send_confirmation_payload(
                    account_id=account_id,
                    send_tool="reply_in_dialog" if message_id is not None else "send_dialog_message",
                    chat=chat,
                    text=text,
                    parse_mode=parse_mode or None,
                    message_id=message_id,
                ),
            )
        if message_id is not None:
            return await self.reply_in_dialog(
                chat=chat,
                message_id=message_id,
                text=text,
                parse_mode=parse_mode or "md",
                confirmation_token=None,
                _skip_confirmation=True,
            )
        return await self.send_message(
            chat=self._coerce_dialog_query(chat),
            text=text,
            parse_mode=parse_mode or "md",
        )

    async def send_dialog_message(
        self,
        chat: str | int,
        text: str,
        parse_mode: str = "md",
        confirmation_token: str | None = None,
        *,
        _skip_confirmation: bool = False,
    ) -> MessageInfo:
        if not _skip_confirmation and (self._write_approval_required() or confirmation_token):
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
        *,
        _skip_confirmation: bool = False,
    ) -> MessageInfo:
        if not _skip_confirmation and (self._write_approval_required() or confirmation_token):
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
