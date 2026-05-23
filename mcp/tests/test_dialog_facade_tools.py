import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from telegram_mcp import server
from telegram_mcp.types import (
    DialogContextResult,
    DialogFileSendPreparation,
    DialogHandle,
    DialogReadRange,
    DialogReadResult,
    DialogReplyPreparation,
    DialogSendPreparation,
    MessageInfo,
)


def _run(awaitable):
    import asyncio

    return asyncio.run(awaitable)


class DialogFacadeToolTests(unittest.TestCase):
    def test_resolve_dialog_returns_dialog_handle(self):
        wrapper = AsyncMock()
        wrapper.resolve_dialog.return_value = DialogHandle(
            dialog_ref="tg://dialog/user/1",
            id=1,
            name="Andrei",
            type="user",
            username="example_user",
            resolved_from="@example_user",
            match_confidence=1.0,
        )

        with patch("telegram_mcp.runtime.get_tg", AsyncMock(return_value=wrapper)):
            result = _run(server.resolve_dialog("@example_user"))

        self.assertEqual(result.dialog_ref, "tg://dialog/user/1")
        wrapper.resolve_dialog.assert_awaited_once_with("@example_user")

    def test_find_dialog_aliases_resolve_dialog(self):
        wrapper = AsyncMock()
        wrapper.resolve_dialog.return_value = DialogHandle(
            dialog_ref="tg://dialog/user/1",
            id=1,
            name="Andrei",
            type="user",
            username="example_user",
            resolved_from="@example_user",
        )

        with patch("telegram_mcp.runtime.get_tg", AsyncMock(return_value=wrapper)):
            result = _run(server.find_dialog("@example_user"))

        self.assertEqual(result.dialog_ref, "tg://dialog/user/1")
        wrapper.resolve_dialog.assert_awaited_once_with("@example_user")

    def test_read_dialog_by_date_returns_dialog_read_result(self):
        wrapper = AsyncMock()
        wrapper.read_dialog_by_date.return_value = DialogReadResult(
            chat=DialogHandle(
                dialog_ref="tg://dialog/user/1",
                id=1,
                name="Andrei",
                type="user",
                username="example_user",
                resolved_from="@example_user",
            ),
            messages=[],
            message_count=0,
            range=DialogReadRange(date_from="2026-04-17", date_to="2026-04-17"),
        )

        with patch("telegram_mcp.runtime.get_tg", AsyncMock(return_value=wrapper)):
            result = _run(
                server.read_dialog_by_date(
                    chat="@example_user",
                    date_from="2026-04-17",
                    date_to="2026-04-17",
                    page_size=25,
                )
            )

        self.assertEqual(result.range.date_from, "2026-04-17")
        wrapper.read_dialog_by_date.assert_awaited_once_with(
            chat="@example_user",
            date_from="2026-04-17",
            date_to="2026-04-17",
            total_limit=25,
            offset_id=0,
            include_voice_transcription=True,
            max_voice_transcriptions=None,
            include_sender_name=True,
        )

    def test_read_dialog_by_date_passes_offset_id(self):
        wrapper = AsyncMock()
        wrapper.read_dialog_by_date.return_value = DialogReadResult(
            chat=DialogHandle(
                dialog_ref="tg://dialog/user/1",
                id=1,
                name="Andrei",
                type="user",
                username="example_user",
                resolved_from="@example_user",
            ),
            messages=[],
            message_count=0,
        )

        with patch("telegram_mcp.runtime.get_tg", AsyncMock(return_value=wrapper)):
            _run(
                server.read_dialog_by_date(
                    chat="@example_user",
                    date_from="2026-04-17",
                    date_to="2026-04-17",
                    page_size=25,
                    offset_id=111,
                )
            )

        wrapper.read_dialog_by_date.assert_awaited_once_with(
            chat="@example_user",
            date_from="2026-04-17",
            date_to="2026-04-17",
            total_limit=25,
            offset_id=111,
            include_voice_transcription=True,
            max_voice_transcriptions=None,
            include_sender_name=True,
        )

    def test_read_dialog_by_date_passes_voice_transcription_budget(self):
        wrapper = AsyncMock()
        wrapper.read_dialog_by_date.return_value = DialogReadResult(
            chat=DialogHandle(
                dialog_ref="tg://dialog/user/1",
                id=1,
                name="Andrei",
                type="user",
                username="example_user",
                resolved_from="@example_user",
            ),
            messages=[],
            message_count=0,
        )

        with patch("telegram_mcp.runtime.get_tg", AsyncMock(return_value=wrapper)):
            _run(
                server.read_dialog_by_date(
                    chat="@example_user",
                    date_from="2026-04-17",
                    date_to="2026-04-17",
                    max_voice_transcriptions=3,
                )
            )

        wrapper.read_dialog_by_date.assert_awaited_once_with(
            chat="@example_user",
            date_from="2026-04-17",
            date_to="2026-04-17",
            total_limit=50,
            offset_id=0,
            include_voice_transcription=True,
            max_voice_transcriptions=3,
            include_sender_name=True,
        )

    def test_read_today_dialog_uses_facade_method(self):
        wrapper = AsyncMock()
        wrapper.read_today_dialog.return_value = DialogReadResult(
            chat=DialogHandle(
                dialog_ref="tg://dialog/user/1",
                id=1,
                name="Andrei",
                type="user",
                username="example_user",
                resolved_from="@example_user",
            ),
            messages=[],
            message_count=0,
        )

        with patch("telegram_mcp.runtime.get_tg", AsyncMock(return_value=wrapper)):
            result = _run(
                server.read_today_dialog(
                    chat="@example_user",
                    day="2026-05-09",
                    limit=25,
                )
            )

        self.assertEqual(result.chat.username, "example_user")
        wrapper.read_today_dialog.assert_awaited_once_with(
            chat="@example_user",
            day="2026-05-09",
            limit=25,
            offset_id=0,
            include_voice_transcription=True,
            max_voice_transcriptions=None,
            include_sender_name=True,
        )

    def test_read_recent_dialog_returns_dialog_read_result(self):
        wrapper = AsyncMock()
        wrapper.read_recent_dialog.return_value = DialogReadResult(
            chat=DialogHandle(
                dialog_ref="tg://dialog/user/1",
                id=1,
                name="Andrei",
                type="user",
                username="example_user",
                resolved_from="@example_user",
            ),
            messages=[],
            message_count=0,
        )

        with patch("telegram_mcp.runtime.get_tg", AsyncMock(return_value=wrapper)):
            result = _run(server.read_recent_dialog(chat="@example_user", limit=10))

        self.assertEqual(result.chat.username, "example_user")
        wrapper.read_recent_dialog.assert_awaited_once_with(
            chat="@example_user",
            limit=10,
            offset_id=0,
            include_voice_transcription=True,
            max_voice_transcriptions=None,
            include_sender_name=True,
        )

    def test_read_dialog_alias_uses_today_when_day_is_provided(self):
        wrapper = AsyncMock()
        wrapper.read_today_dialog.return_value = DialogReadResult(
            chat=DialogHandle(
                dialog_ref="tg://dialog/user/1",
                id=1,
                name="Andrei",
                type="user",
                username="example_user",
                resolved_from="@example_user",
            ),
            messages=[],
            message_count=0,
        )

        with patch("telegram_mcp.runtime.get_tg", AsyncMock(return_value=wrapper)):
            result = _run(
                server.read_dialog(
                    chat="@example_user",
                    day="2026-05-09",
                    limit=10,
                )
            )

        self.assertEqual(result.chat.username, "example_user")
        wrapper.read_today_dialog.assert_awaited_once_with(
            chat="@example_user",
            day="2026-05-09",
            limit=10,
            offset_id=0,
            include_voice_transcription=True,
            max_voice_transcriptions=None,
            include_sender_name=True,
        )

    def test_read_dialog_alias_uses_recent_without_day(self):
        wrapper = AsyncMock()
        wrapper.read_recent_dialog.return_value = DialogReadResult(
            chat=DialogHandle(
                dialog_ref="tg://dialog/user/1",
                id=1,
                name="Andrei",
                type="user",
                username="example_user",
                resolved_from="@example_user",
            ),
            messages=[],
            message_count=0,
        )

        with patch("telegram_mcp.runtime.get_tg", AsyncMock(return_value=wrapper)):
            result = _run(server.read_dialog(chat="@example_user", limit=10))

        self.assertEqual(result.chat.username, "example_user")
        wrapper.read_recent_dialog.assert_awaited_once_with(
            chat="@example_user",
            limit=10,
            offset_id=0,
            include_voice_transcription=True,
            max_voice_transcriptions=None,
            include_sender_name=True,
        )

    def test_read_recent_dialog_passes_offset_id(self):
        wrapper = AsyncMock()
        wrapper.read_recent_dialog.return_value = DialogReadResult(
            chat=DialogHandle(
                dialog_ref="tg://dialog/user/1",
                id=1,
                name="Andrei",
                type="user",
                username="example_user",
                resolved_from="@example_user",
            ),
            messages=[],
            message_count=0,
        )

        with patch("telegram_mcp.runtime.get_tg", AsyncMock(return_value=wrapper)):
            _run(server.read_recent_dialog(chat="@example_user", limit=10, offset_id=222))

        wrapper.read_recent_dialog.assert_awaited_once_with(
            chat="@example_user",
            limit=10,
            offset_id=222,
            include_voice_transcription=True,
            max_voice_transcriptions=None,
            include_sender_name=True,
        )

    def test_read_recent_dialog_can_disable_voice_transcription(self):
        wrapper = AsyncMock()
        wrapper.read_recent_dialog.return_value = DialogReadResult(
            chat=DialogHandle(
                dialog_ref="tg://dialog/user/1",
                id=1,
                name="Andrei",
                type="user",
                username="example_user",
                resolved_from="@example_user",
            ),
            messages=[],
            message_count=0,
        )

        with patch("telegram_mcp.runtime.get_tg", AsyncMock(return_value=wrapper)):
            _run(
                server.read_recent_dialog(
                    chat="@example_user",
                    limit=10,
                    include_voice_transcription=False,
                )
            )

        wrapper.read_recent_dialog.assert_awaited_once_with(
            chat="@example_user",
            limit=10,
            offset_id=0,
            include_voice_transcription=False,
            max_voice_transcriptions=None,
            include_sender_name=True,
        )

    def test_read_recent_dialog_can_disable_sender_names(self):
        wrapper = AsyncMock()
        wrapper.read_recent_dialog.return_value = DialogReadResult(
            chat=DialogHandle(
                dialog_ref="tg://dialog/user/1",
                id=1,
                name="Andrei",
                type="user",
                username="example_user",
                resolved_from="@example_user",
            ),
            messages=[],
            message_count=0,
        )

        with patch("telegram_mcp.runtime.get_tg", AsyncMock(return_value=wrapper)):
            _run(
                server.read_recent_dialog(
                    chat="@example_user",
                    include_sender_name=False,
                )
            )

        wrapper.read_recent_dialog.assert_awaited_once_with(
            chat="@example_user",
            limit=50,
            offset_id=0,
            include_voice_transcription=True,
            max_voice_transcriptions=None,
            include_sender_name=False,
        )

    def test_search_dialog_messages_returns_dialog_read_result(self):
        wrapper = AsyncMock()
        wrapper.search_dialog_messages.return_value = DialogReadResult(
            chat=DialogHandle(
                dialog_ref="tg://dialog/user/1",
                id=1,
                name="Andrei",
                type="user",
                username="example_user",
                resolved_from="@example_user",
            ),
            messages=[],
            message_count=0,
        )

        with patch("telegram_mcp.runtime.get_tg", AsyncMock(return_value=wrapper)):
            result = _run(
                server.search_dialog_messages(
                    chat="@example_user",
                    query="hello",
                    limit=5,
                )
            )

        self.assertEqual(result.chat.username, "example_user")
        wrapper.search_dialog_messages.assert_awaited_once_with(
            chat="@example_user",
            query="hello",
            limit=5,
            include_sender_name=True,
        )

    def test_collect_dialog_context_uses_facade_method(self):
        wrapper = AsyncMock()
        wrapper.collect_dialog_context.return_value = DialogContextResult(
            chat=DialogHandle(
                dialog_ref="tg://dialog/user/1",
                id=1,
                name="Andrei",
                type="user",
                username="example_user",
                resolved_from="@example_user",
            ),
            messages=[],
            message_count=0,
        )

        with patch("telegram_mcp.runtime.get_tg", AsyncMock(return_value=wrapper)):
            result = _run(
                server.collect_dialog_context(
                    chat="@example_user",
                    mode="fast",
                    recent_limit=10,
                    include_pinned=False,
                )
            )

        self.assertEqual(result.collection_mode, "fast")
        wrapper.collect_dialog_context.assert_awaited_once_with(
            chat="@example_user",
            mode="fast",
            recent_limit=10,
            date_from=None,
            date_to=None,
            offset_id=0,
            include_pinned=False,
            pinned_limit=5,
            include_voice_transcription=None,
            max_voice_transcriptions=None,
        )

    def test_collect_context_aliases_collect_dialog_context(self):
        wrapper = AsyncMock()
        wrapper.collect_dialog_context.return_value = DialogContextResult(
            chat=DialogHandle(
                dialog_ref="tg://dialog/user/1",
                id=1,
                name="Andrei",
                type="user",
                username="example_user",
                resolved_from="@example_user",
            ),
            messages=[],
            message_count=0,
        )

        with patch("telegram_mcp.runtime.get_tg", AsyncMock(return_value=wrapper)):
            result = _run(server.collect_context(chat="@example_user", recent_limit=10))

        self.assertEqual(result.chat.username, "example_user")
        wrapper.collect_dialog_context.assert_awaited_once_with(
            chat="@example_user",
            mode="fast",
            recent_limit=10,
            date_from=None,
            date_to=None,
            offset_id=0,
            include_pinned=True,
            pinned_limit=5,
            include_voice_transcription=None,
            max_voice_transcriptions=None,
        )

    def test_prepare_dialog_reply_uses_facade_method(self):
        wrapper = AsyncMock()
        context = DialogContextResult(
            chat=DialogHandle(
                dialog_ref="tg://dialog/user/1",
                id=1,
                name="Andrei",
                type="user",
                username="example_user",
                resolved_from="@example_user",
            ),
            messages=[],
            message_count=0,
        )
        wrapper.prepare_dialog_reply.return_value = DialogReplyPreparation(
            chat=context.chat,
            goal="reply",
            context=context,
            send_tool="send_dialog_message",
            send_args_preview={"chat": "tg://dialog/user/1", "text": ""},
        )

        with patch("telegram_mcp.runtime.get_tg", AsyncMock(return_value=wrapper)):
            result = _run(
                server.prepare_dialog_reply(
                    chat="@example_user",
                    goal="reply",
                    draft_text="hello",
                )
            )

        self.assertTrue(result.preview_only)
        wrapper.prepare_dialog_reply.assert_awaited_once_with(
            chat="@example_user",
            goal="reply",
            reply_to_message_id=None,
            context_limit=20,
            mode="fast",
            draft_text="hello",
        )

    def test_draft_reply_aliases_prepare_dialog_reply(self):
        wrapper = AsyncMock()
        context = DialogContextResult(
            chat=DialogHandle(
                dialog_ref="tg://dialog/user/1",
                id=1,
                name="Andrei",
                type="user",
                username="example_user",
                resolved_from="@example_user",
            ),
            messages=[],
            message_count=0,
        )
        wrapper.prepare_dialog_reply.return_value = DialogReplyPreparation(
            chat=context.chat,
            goal="reply",
            context=context,
            send_tool="send_dialog_message",
            send_args_preview={"chat": "tg://dialog/user/1", "text": ""},
        )

        with patch("telegram_mcp.runtime.get_tg", AsyncMock(return_value=wrapper)):
            result = _run(server.draft_reply(chat="@example_user", goal="reply"))

        self.assertTrue(result.preview_only)
        wrapper.prepare_dialog_reply.assert_awaited_once_with(
            chat="@example_user",
            goal="reply",
            reply_to_message_id=None,
            context_limit=20,
            mode="fast",
            draft_text=None,
        )

    def test_prepare_send_message_is_preview_only(self):
        wrapper = AsyncMock()
        wrapper.prepare_send_message.return_value = DialogSendPreparation(
            chat=DialogHandle(
                dialog_ref="tg://dialog/user/1",
                id=1,
                name="Andrei",
                type="user",
                username="example_user",
                resolved_from="@example_user",
            ),
            text="hello",
            send_tool="send_dialog_message",
            send_args_preview={"chat": "tg://dialog/user/1", "text": "hello"},
        )

        with patch("telegram_mcp.runtime.get_tg", AsyncMock(return_value=wrapper)):
            result = _run(
                server.prepare_send_message(chat="@example_user", text="hello")
            )

        self.assertTrue(result.preview_only)
        wrapper.prepare_send_message.assert_awaited_once_with(
            chat="@example_user",
            text="hello",
            parse_mode="md",
        )

    def test_prepare_reply_message_is_preview_only(self):
        wrapper = AsyncMock()
        wrapper.prepare_reply_message.return_value = DialogSendPreparation(
            chat=DialogHandle(
                dialog_ref="tg://dialog/user/1",
                id=1,
                name="Andrei",
                type="user",
                username="example_user",
                resolved_from="@example_user",
            ),
            text="pong",
            reply_target_message_id=3,
            send_tool="reply_in_dialog",
            send_args_preview={
                "chat": "tg://dialog/user/1",
                "message_id": 3,
                "text": "pong",
            },
        )

        with patch("telegram_mcp.runtime.get_tg", AsyncMock(return_value=wrapper)):
            result = _run(
                server.prepare_reply_message(
                    chat="@example_user",
                    message_id=3,
                    text="pong",
                )
            )

        self.assertTrue(result.preview_only)
        wrapper.prepare_reply_message.assert_awaited_once_with(
            chat="@example_user",
            message_id=3,
            text="pong",
            parse_mode="md",
        )

    def test_prepare_send_file_is_preview_only(self):
        wrapper = AsyncMock()
        wrapper.prepare_send_file.return_value = DialogFileSendPreparation(
            chat=DialogHandle(
                dialog_ref="tg://dialog/user/1",
                id=1,
                name="Andrei",
                type="user",
                username="example_user",
                resolved_from="@example_user",
            ),
            file_path="/tmp/demo.txt",
            file_name="demo.txt",
            caption="hi",
            send_tool="send_file",
            send_args_preview={
                "chat": "tg://dialog/user/1",
                "file_path": "/tmp/demo.txt",
                "caption": "hi",
                "parse_mode": "md",
            },
            preview_token="abcd1234abcd1234",
            warnings=["preview_only: this tool validates and prepares file send arguments but never sends."],
        )

        with patch("telegram_mcp.runtime.get_tg", AsyncMock(return_value=wrapper)):
            result = _run(
                server.prepare_send_file(
                    chat="@example_user",
                    file_path="/tmp/demo.txt",
                    caption="hi",
                )
            )

        self.assertTrue(result.preview_only)
        wrapper.prepare_send_file.assert_awaited_once_with(
            chat="@example_user",
            file_path="/tmp/demo.txt",
            caption="hi",
            parse_mode="md",
        )

    def test_send_dialog_message_uses_facade_method(self):
        wrapper = AsyncMock()
        wrapper.send_dialog_message.return_value = MessageInfo(
            id=7,
            chat_id=1,
            date=datetime(2026, 4, 17, tzinfo=timezone.utc),
            text="hello",
            is_outgoing=True,
        )

        with patch("telegram_mcp.runtime.get_tg", AsyncMock(return_value=wrapper)):
            result = _run(server.send_dialog_message(chat="@example_user", text="hello"))

        self.assertEqual(result.text, "hello")
        wrapper.send_dialog_message.assert_awaited_once_with(
            chat="@example_user",
            text="hello",
            parse_mode="md",
        )

    def test_reply_in_dialog_uses_facade_method(self):
        wrapper = AsyncMock()
        wrapper.reply_in_dialog.return_value = MessageInfo(
            id=8,
            chat_id=1,
            date=datetime(2026, 4, 17, tzinfo=timezone.utc),
            text="pong",
            reply_to_msg_id=3,
            is_outgoing=True,
        )

        with patch("telegram_mcp.runtime.get_tg", AsyncMock(return_value=wrapper)):
            result = _run(
                server.reply_in_dialog(
                    chat="@example_user",
                    message_id=3,
                    text="pong",
                )
            )

        self.assertEqual(result.reply_to_msg_id, 3)
        wrapper.reply_in_dialog.assert_awaited_once_with(
            chat="@example_user",
            message_id=3,
            text="pong",
            parse_mode="md",
        )

    def test_reply_message_aliases_reply_in_dialog(self):
        wrapper = AsyncMock()
        wrapper.reply_in_dialog.return_value = MessageInfo(
            id=8,
            chat_id=1,
            date=datetime(2026, 4, 17, tzinfo=timezone.utc),
            text="pong",
            reply_to_msg_id=3,
            is_outgoing=True,
        )

        with patch("telegram_mcp.runtime.get_tg", AsyncMock(return_value=wrapper)):
            result = _run(
                server.reply_message(
                    chat="@example_user",
                    message_id=3,
                    text="pong",
                )
            )

        self.assertEqual(result.reply_to_msg_id, 3)
        wrapper.reply_in_dialog.assert_awaited_once_with(
            chat="@example_user",
            message_id=3,
            text="pong",
            parse_mode="md",
        )
