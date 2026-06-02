"""Message write operations for TelegramWrapper."""

from __future__ import annotations

import os

from telethon.tl.functions.messages import SendMediaRequest, SendReactionRequest
from telethon.tl.types import InputMediaPoll, Poll, PollAnswer, ReactionEmoji

from .types import MessageInfo, PollInfo


class MessageWriteMixin:
    """Explicit Telegram write operations."""

    async def send_message(
        self,
        chat: str,
        text: str,
        parse_mode: str = "md",
    ) -> MessageInfo:
        entity = await self._resolve_entity(chat)
        msg = await self._run_write(
            "send_message",
            lambda: self.client.send_message(entity, text, parse_mode=parse_mode),
        )
        self._invalidate_after_dialog_write()
        return self._message_to_info(
            msg,
            default_chat_id=entity.id,
            is_outgoing=True,
        )

    async def reply_to_message(
        self,
        chat: str,
        message_id: int,
        text: str,
        parse_mode: str = "md",
    ) -> MessageInfo:
        entity = await self._resolve_entity(chat)
        msg = await self._run_write(
            "reply_to_message",
            lambda: self.client.send_message(
                entity, text, reply_to=message_id, parse_mode=parse_mode
            ),
        )
        self._invalidate_after_dialog_write()
        return self._message_to_info(
            msg,
            default_chat_id=entity.id,
            reply_to_msg_id=message_id,
            is_outgoing=True,
        )

    async def edit_message(
        self,
        chat: str,
        message_id: int,
        text: str,
        parse_mode: str = "md",
    ) -> MessageInfo:
        entity = await self._resolve_entity(chat)
        msg = await self._run_write(
            "edit_message",
            lambda: self.client.edit_message(
                entity, message_id, text, parse_mode=parse_mode
            ),
        )
        self._invalidate_after_dialog_write()
        return self._message_to_info(
            msg,
            default_chat_id=entity.id,
            is_outgoing=True,
        )

    async def delete_messages(
        self, chat: str | int, message_ids: list[int], revoke: bool = True
    ) -> int:
        entity = await self._resolve_entity(chat)
        await self._run_write(
            "delete_messages",
            lambda: self.client.delete_messages(entity, message_ids, revoke=revoke),
        )
        # result is a list of AffectedMessages
        self._invalidate_after_dialog_write()
        return len(message_ids)

    async def forward_messages(
        self, from_chat: str | int, to_chat: str | int, message_ids: list[int]
    ) -> list[MessageInfo]:
        from_entity = await self._resolve_entity(from_chat)
        to_entity = await self._resolve_entity(to_chat)
        msgs = await self._run_write(
            "forward_messages",
            lambda: self.client.forward_messages(to_entity, message_ids, from_entity),
        )
        self._invalidate_after_dialog_write()
        if not isinstance(msgs, list):
            msgs = [msgs]
        result = []
        for msg in msgs:
            result.append(
                self._message_to_info(
                    msg,
                    default_chat_id=to_entity.id,
                    is_outgoing=True,
                )
            )
        return result

    async def pin_message(
        self, chat: str | int, message_id: int, notify: bool = False
    ) -> bool:
        entity = await self._resolve_entity(chat)
        await self._run_write(
            "pin_message",
            lambda: self.client.pin_message(entity, message_id, notify=notify),
        )
        self._invalidate_after_dialog_write()
        return True

    async def unpin_message(
        self, chat: str | int, message_id: int | None = None
    ) -> bool:
        entity = await self._resolve_entity(chat)
        await self._run_write(
            "unpin_message",
            lambda: self.client.unpin_message(entity, message_id),
        )
        self._invalidate_after_dialog_write()
        return True

    # ── Reactions ──

    async def send_reaction(
        self, chat: str | int, message_id: int, emoji: str
    ) -> bool:
        entity = await self._resolve_entity(chat)
        peer = await self.client.get_input_entity(entity)
        await self._run_write(
            "send_reaction",
            lambda: self.client(
                SendReactionRequest(
                    peer=peer,
                    msg_id=message_id,
                    reaction=[ReactionEmoji(emoticon=emoji)],
                )
            ),
        )
        self._invalidate_after_dialog_write()
        return True

    # ── Utilities ──

    async def mark_as_read(self, chat: str | int) -> bool:
        entity = await self._resolve_entity(chat)
        await self._run_write(
            "mark_as_read",
            lambda: self.client.send_read_acknowledge(entity),
        )
        self._invalidate_chat_list_cache()
        return True

    # ── Message links ──

    # ── Polls ──

    async def create_poll(
        self,
        chat: str | int,
        question: str,
        options: list[str],
        multiple_choice: bool = False,
        quiz_mode: bool = False,
        correct_option: int | None = None,
        public_voters: bool = True,
    ) -> PollInfo:
        entity = await self._resolve_entity(chat)
        peer = await self.client.get_input_entity(entity)

        poll_answers = [
            PollAnswer(text=opt, option=bytes([i]))
            for i, opt in enumerate(options)
        ]
        poll = Poll(
            id=0,
            question=question,
            answers=poll_answers,
            multiple_choice=multiple_choice,
            quiz=quiz_mode,
            public_voters=public_voters,
            hash=0,
        )
        media = InputMediaPoll(
            poll=poll,
            correct_answers=[bytes([correct_option])] if quiz_mode and correct_option is not None else None,
        )
        result = await self._run_write(
            "create_poll",
            lambda: self.client(
                SendMediaRequest(
                    peer=peer,
                    media=media,
                    message="",
                    random_id=int.from_bytes(os.urandom(8), "big", signed=True),
                )
            ),
        )
        self._invalidate_after_dialog_write()
        msg = result.updates[-1].message if hasattr(result, "updates") else None
        msg_id = msg.id if msg else 0
        chat_id = entity.id

        return PollInfo(
            message_id=msg_id,
            chat_id=chat_id,
            question=question,
            options=options,
            is_quiz=quiz_mode,
            multiple_choice=multiple_choice,
            public_voters=public_voters,
        )


    # ── Inline buttons ──

    async def send_message_with_buttons(
        self,
        chat: str | int,
        text: str,
        buttons: list[list[dict[str, str]]],
        parse_mode: str | None = "md",
    ) -> MessageInfo:
        """Send a message with inline keyboard buttons.

        buttons format: [[{"text": "Label", "url": "https://..."}], [...]]
        Each inner list is a row. Each button has "text" and optionally "url" or "data".
        """
        from telethon.tl.types import (
            KeyboardButtonCallback,
            KeyboardButtonUrl,
            ReplyInlineMarkup,
            KeyboardButtonRow,
        )

        rows = []
        for row in buttons:
            btn_list = []
            for btn in row:
                if "url" in btn:
                    btn_list.append(KeyboardButtonUrl(text=btn["text"], url=btn["url"]))
                elif "data" in btn:
                    btn_list.append(
                        KeyboardButtonCallback(text=btn["text"], data=btn["data"].encode())
                    )
            if btn_list:
                rows.append(KeyboardButtonRow(buttons=btn_list))

        markup = ReplyInlineMarkup(rows=rows) if rows else None

        entity = await self._resolve_entity(chat)
        msg = await self._run_write(
            "send_message_with_buttons",
            lambda: self.client.send_message(
                entity, text, parse_mode=parse_mode, buttons=markup
            ),
        )
        self._invalidate_after_dialog_write()
        return self._message_to_info(
            msg,
            default_chat_id=entity.id,
            is_outgoing=True,
        )
