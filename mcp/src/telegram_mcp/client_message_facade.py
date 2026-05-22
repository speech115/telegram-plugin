"""Task-shaped dialog facade helpers for TelegramWrapper."""

from __future__ import annotations

from .errors import ToolContractError
from .types import (
    DialogContextResult,
    DialogReplyPreparation,
    DialogSendPreparation,
    MessageInfo,
)


class MessageFacadeMixin:
    """Agent-facing dialog facade and preview helpers."""

    async def collect_dialog_context(
        self,
        chat: str | int,
        *,
        mode: str = "fast",
        recent_limit: int = 50,
        date_from: str | None = None,
        date_to: str | None = None,
        offset_id: int = 0,
        include_pinned: bool = True,
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
        send_tool = "reply_in_dialog" if reply_to_message_id is not None else "send_dialog_message"
        send_args_preview: dict[str, object] = {
            "chat": context.chat.dialog_ref,
            "text": draft_text or "",
        }
        if reply_to_message_id is not None:
            send_args_preview["message_id"] = reply_to_message_id

        warnings = [
            "preview_only: this tool never sends messages; use the explicit send/reply tool after review."
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
        )

    async def prepare_send_message(
        self,
        chat: str | int,
        text: str,
        parse_mode: str = "md",
    ) -> DialogSendPreparation:
        handle = await self.resolve_dialog(chat)
        return DialogSendPreparation(
            chat=handle,
            text=text,
            parse_mode=parse_mode or None,
            preview_only=True,
            send_tool="send_dialog_message",
            send_args_preview={
                "chat": handle.dialog_ref,
                "text": text,
                "parse_mode": parse_mode or None,
            },
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
        return DialogSendPreparation(
            chat=handle,
            text=text,
            parse_mode=parse_mode or None,
            reply_target_message_id=message_id,
            preview_only=True,
            send_tool="reply_in_dialog",
            send_args_preview={
                "chat": handle.dialog_ref,
                "message_id": message_id,
                "text": text,
                "parse_mode": parse_mode or None,
            },
        )

    async def send_dialog_message(
        self,
        chat: str | int,
        text: str,
        parse_mode: str = "md",
    ) -> MessageInfo:
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
    ) -> MessageInfo:
        return await self.reply_to_message(
            chat=self._coerce_dialog_query(chat),
            message_id=message_id,
            text=text,
            parse_mode=parse_mode,
        )
