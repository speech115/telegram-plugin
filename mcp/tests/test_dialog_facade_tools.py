import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from telegram_mcp import server
from telegram_mcp.tools.dialog_facade_tools import telegram_export_members
from telegram_mcp.types import (
    DialogContextResult,
    DialogHandle,
    DialogLatestMessageResult,
    DialogMessageByIdResult,
    DialogMetadataListResult,
    DialogMetadataResult,
    DialogReadRange,
    DialogReadResult,
    DialogReplyPreparation,
    DialogSendPreparation,
    DialogPostCountResult,
    MessageInfo,
    Participant,
    ChatInfo,
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
            username="targetdaddy",
            resolved_from="@targetdaddy",
            match_confidence=1.0,
        )

        with patch("telegram_mcp.runtime.get_tg", AsyncMock(return_value=wrapper)):
            result = _run(server.resolve_dialog("@targetdaddy"))

        self.assertEqual(result.dialog_ref, "tg://dialog/user/1")
        wrapper.resolve_dialog.assert_awaited_once_with("@targetdaddy")

    def test_find_dialog_aliases_resolve_dialog(self):
        wrapper = AsyncMock()
        wrapper.resolve_dialog.return_value = DialogHandle(
            dialog_ref="tg://dialog/user/1",
            id=1,
            name="Andrei",
            type="user",
            username="targetdaddy",
            resolved_from="@targetdaddy",
        )

        with patch("telegram_mcp.runtime.get_tg", AsyncMock(return_value=wrapper)):
            result = _run(server.find_dialog("@targetdaddy"))

        self.assertEqual(result.dialog_ref, "tg://dialog/user/1")
        wrapper.resolve_dialog.assert_awaited_once_with("@targetdaddy")

    def test_telegram_count_posts_returns_metadata_without_history_download(self):
        wrapper = AsyncMock()
        wrapper.count_dialog_metadata.return_value = DialogPostCountResult(
            chat=DialogHandle(
                dialog_ref="tg://dialog/channel/1",
                id=1,
                name="Channel",
                type="channel",
                username="targetchannel",
                resolved_from="@targetchannel",
            ),
            total=123,
        )

        with patch("telegram_mcp.runtime.get_tg", AsyncMock(return_value=wrapper)):
            result = _run(server.telegram_count_posts("@targetchannel"))

        self.assertEqual(result.total, 123)
        self.assertEqual(result.data_source, "live_telegram")
        wrapper.count_dialog_metadata.assert_awaited_once_with(chat="@targetchannel", count_type="posts")

    def test_filtered_metadata_counts_use_shared_helper(self):
        wrapper = AsyncMock()
        wrapper.count_dialog_metadata.return_value = DialogPostCountResult(
            chat=DialogHandle(
                dialog_ref="tg://dialog/channel/1",
                id=1,
                name="Channel",
                type="channel",
                username="targetchannel",
                resolved_from="@targetchannel",
            ),
            total=5,
            count_type="videos",
            filter="InputMessagesFilterVideo",
        )

        with patch("telegram_mcp.runtime.get_tg", AsyncMock(return_value=wrapper)):
            result = _run(server.telegram_count_videos("@targetchannel"))

        self.assertEqual(result.total, 5)
        self.assertEqual(result.count_type, "videos")
        wrapper.count_dialog_metadata.assert_awaited_once_with(chat="@targetchannel", count_type="videos")

    def test_filtered_metadata_lists_use_shared_helper(self):
        wrapper = AsyncMock()
        wrapper.list_dialog_metadata.return_value = DialogMetadataListResult(
            chat=DialogHandle(
                dialog_ref="tg://dialog/channel/1",
                id=1,
                name="Channel",
                type="channel",
                username="targetchannel",
                resolved_from="@targetchannel",
            ),
            messages=[],
            list_type="links",
            filter="InputMessagesFilterUrl",
        )

        with patch("telegram_mcp.runtime.get_tg", AsyncMock(return_value=wrapper)):
            result = _run(server.telegram_list_links("@targetchannel", limit=10, offset_id=42))

        self.assertEqual(result.list_type, "links")
        wrapper.list_dialog_metadata.assert_awaited_once_with(
            chat="@targetchannel",
            list_type="links",
            limit=10,
            offset_id=42,
            include_sender_name=False,
        )

    def test_metadata_latest_info_and_message_tools(self):
        handle = DialogHandle(
            dialog_ref="tg://dialog/channel/1",
            id=1,
            name="Channel",
            type="channel",
            username="targetchannel",
            resolved_from="@targetchannel",
        )
        wrapper = AsyncMock()
        wrapper.latest_dialog_message.return_value = DialogLatestMessageResult(chat=handle, message=None)
        wrapper.dialog_metadata.return_value = DialogMetadataResult(
            chat=handle,
            info=ChatInfo(id=1, name="Channel", type="channel", username="targetchannel"),
        )
        wrapper.get_dialog_message.return_value = DialogMessageByIdResult(chat=handle, message_id=42, message=None)

        with patch("telegram_mcp.runtime.get_tg", AsyncMock(return_value=wrapper)):
            latest = _run(server.telegram_latest_message("@targetchannel"))
            info = _run(server.telegram_dialog_metadata("@targetchannel"))
            message = _run(server.telegram_get_message("@targetchannel", 42))

        self.assertIsNone(latest.message)
        self.assertEqual(info.info.username, "targetchannel")
        self.assertEqual(message.message_id, 42)
        wrapper.latest_dialog_message.assert_awaited_once_with(chat="@targetchannel")
        wrapper.dialog_metadata.assert_awaited_once_with(chat="@targetchannel")
        wrapper.get_dialog_message.assert_awaited_once_with(chat="@targetchannel", message_id=42)

    def test_read_dialog_by_date_returns_dialog_read_result(self):
        wrapper = AsyncMock()
        wrapper.read_dialog_by_date.return_value = DialogReadResult(
            chat=DialogHandle(
                dialog_ref="tg://dialog/user/1",
                id=1,
                name="Andrei",
                type="user",
                username="targetdaddy",
                resolved_from="@targetdaddy",
            ),
            messages=[],
            message_count=0,
            range=DialogReadRange(date_from="2026-04-17", date_to="2026-04-17"),
        )

        with patch("telegram_mcp.runtime.get_tg", AsyncMock(return_value=wrapper)):
            result = _run(
                server.read_dialog_by_date(
                    chat="@targetdaddy",
                    date_from="2026-04-17",
                    date_to="2026-04-17",
                    page_size=25,
                )
            )

        self.assertEqual(result.range.date_from, "2026-04-17")
        wrapper.read_dialog_by_date.assert_awaited_once_with(
            chat="@targetdaddy",
            date_from="2026-04-17",
            date_to="2026-04-17",
            total_limit=25,
            offset_id=0,
            include_voice_transcription=False,
            max_voice_transcriptions=None,
            include_sender_name=False,
        )

    def test_read_dialog_by_date_passes_offset_id(self):
        wrapper = AsyncMock()
        wrapper.read_dialog_by_date.return_value = DialogReadResult(
            chat=DialogHandle(
                dialog_ref="tg://dialog/user/1",
                id=1,
                name="Andrei",
                type="user",
                username="targetdaddy",
                resolved_from="@targetdaddy",
            ),
            messages=[],
            message_count=0,
        )

        with patch("telegram_mcp.runtime.get_tg", AsyncMock(return_value=wrapper)):
            _run(
                server.read_dialog_by_date(
                    chat="@targetdaddy",
                    date_from="2026-04-17",
                    date_to="2026-04-17",
                    page_size=25,
                    offset_id=111,
                )
            )

        wrapper.read_dialog_by_date.assert_awaited_once_with(
            chat="@targetdaddy",
            date_from="2026-04-17",
            date_to="2026-04-17",
            total_limit=25,
            offset_id=111,
            include_voice_transcription=False,
            max_voice_transcriptions=None,
            include_sender_name=False,
        )

    def test_read_dialog_by_date_passes_voice_transcription_budget(self):
        wrapper = AsyncMock()
        wrapper.read_dialog_by_date.return_value = DialogReadResult(
            chat=DialogHandle(
                dialog_ref="tg://dialog/user/1",
                id=1,
                name="Andrei",
                type="user",
                username="targetdaddy",
                resolved_from="@targetdaddy",
            ),
            messages=[],
            message_count=0,
        )

        with patch("telegram_mcp.runtime.get_tg", AsyncMock(return_value=wrapper)):
            _run(
                server.read_dialog_by_date(
                    chat="@targetdaddy",
                    date_from="2026-04-17",
                    date_to="2026-04-17",
                    max_voice_transcriptions=3,
                )
            )

        wrapper.read_dialog_by_date.assert_awaited_once_with(
            chat="@targetdaddy",
            date_from="2026-04-17",
            date_to="2026-04-17",
            total_limit=20,
            offset_id=0,
            include_voice_transcription=False,
            max_voice_transcriptions=3,
            include_sender_name=False,
        )

    def test_read_today_dialog_uses_facade_method(self):
        wrapper = AsyncMock()
        wrapper.read_today_dialog.return_value = DialogReadResult(
            chat=DialogHandle(
                dialog_ref="tg://dialog/user/1",
                id=1,
                name="Andrei",
                type="user",
                username="targetdaddy",
                resolved_from="@targetdaddy",
            ),
            messages=[],
            message_count=0,
        )

        with patch("telegram_mcp.runtime.get_tg", AsyncMock(return_value=wrapper)):
            result = _run(
                server.read_today_dialog(
                    chat="@targetdaddy",
                    day="2026-05-09",
                    limit=25,
                )
            )

        self.assertEqual(result.chat.username, "targetdaddy")
        wrapper.read_today_dialog.assert_awaited_once_with(
            chat="@targetdaddy",
            day="2026-05-09",
            limit=25,
            offset_id=0,
            include_voice_transcription=False,
            max_voice_transcriptions=None,
            include_sender_name=False,
        )

    def test_read_recent_dialog_returns_dialog_read_result(self):
        wrapper = AsyncMock()
        wrapper.read_recent_dialog.return_value = DialogReadResult(
            chat=DialogHandle(
                dialog_ref="tg://dialog/user/1",
                id=1,
                name="Andrei",
                type="user",
                username="targetdaddy",
                resolved_from="@targetdaddy",
            ),
            messages=[],
            message_count=0,
        )

        with patch("telegram_mcp.runtime.get_tg", AsyncMock(return_value=wrapper)):
            result = _run(server.read_recent_dialog(chat="@targetdaddy", limit=10))

        self.assertEqual(result.chat.username, "targetdaddy")
        wrapper.read_recent_dialog.assert_awaited_once_with(
            chat="@targetdaddy",
            limit=10,
            offset_id=0,
            include_voice_transcription=False,
            max_voice_transcriptions=None,
            include_sender_name=False,
        )

    def test_read_dialog_alias_uses_today_when_day_is_provided(self):
        wrapper = AsyncMock()
        wrapper.read_today_dialog.return_value = DialogReadResult(
            chat=DialogHandle(
                dialog_ref="tg://dialog/user/1",
                id=1,
                name="Andrei",
                type="user",
                username="targetdaddy",
                resolved_from="@targetdaddy",
            ),
            messages=[],
            message_count=0,
        )

        with patch("telegram_mcp.runtime.get_tg", AsyncMock(return_value=wrapper)):
            result = _run(
                server.read_dialog(
                    chat="@targetdaddy",
                    day="2026-05-09",
                    limit=10,
                )
            )

        self.assertEqual(result.chat.username, "targetdaddy")
        wrapper.read_today_dialog.assert_awaited_once_with(
            chat="@targetdaddy",
            day="2026-05-09",
            limit=10,
            offset_id=0,
            include_voice_transcription=False,
            max_voice_transcriptions=None,
            include_sender_name=False,
        )

    def test_read_dialog_alias_uses_recent_without_day(self):
        wrapper = AsyncMock()
        wrapper.read_recent_dialog.return_value = DialogReadResult(
            chat=DialogHandle(
                dialog_ref="tg://dialog/user/1",
                id=1,
                name="Andrei",
                type="user",
                username="targetdaddy",
                resolved_from="@targetdaddy",
            ),
            messages=[],
            message_count=0,
        )

        with patch("telegram_mcp.runtime.get_tg", AsyncMock(return_value=wrapper)):
            result = _run(server.read_dialog(chat="@targetdaddy", limit=10))

        self.assertEqual(result.chat.username, "targetdaddy")
        wrapper.read_recent_dialog.assert_awaited_once_with(
            chat="@targetdaddy",
            limit=10,
            offset_id=0,
            include_voice_transcription=False,
            max_voice_transcriptions=None,
            include_sender_name=False,
        )

    def test_read_recent_dialog_passes_offset_id(self):
        wrapper = AsyncMock()
        wrapper.read_recent_dialog.return_value = DialogReadResult(
            chat=DialogHandle(
                dialog_ref="tg://dialog/user/1",
                id=1,
                name="Andrei",
                type="user",
                username="targetdaddy",
                resolved_from="@targetdaddy",
            ),
            messages=[],
            message_count=0,
        )

        with patch("telegram_mcp.runtime.get_tg", AsyncMock(return_value=wrapper)):
            _run(server.read_recent_dialog(chat="@targetdaddy", limit=10, offset_id=222))

        wrapper.read_recent_dialog.assert_awaited_once_with(
            chat="@targetdaddy",
            limit=10,
            offset_id=222,
            include_voice_transcription=False,
            max_voice_transcriptions=None,
            include_sender_name=False,
        )

    def test_read_recent_dialog_can_disable_voice_transcription(self):
        wrapper = AsyncMock()
        wrapper.read_recent_dialog.return_value = DialogReadResult(
            chat=DialogHandle(
                dialog_ref="tg://dialog/user/1",
                id=1,
                name="Andrei",
                type="user",
                username="targetdaddy",
                resolved_from="@targetdaddy",
            ),
            messages=[],
            message_count=0,
        )

        with patch("telegram_mcp.runtime.get_tg", AsyncMock(return_value=wrapper)):
            _run(
                server.read_recent_dialog(
                    chat="@targetdaddy",
                    limit=10,
                    include_voice_transcription=False,
                )
            )

        wrapper.read_recent_dialog.assert_awaited_once_with(
            chat="@targetdaddy",
            limit=10,
            offset_id=0,
            include_voice_transcription=False,
            max_voice_transcriptions=None,
            include_sender_name=False,
        )

    def test_read_recent_dialog_can_disable_sender_names(self):
        wrapper = AsyncMock()
        wrapper.read_recent_dialog.return_value = DialogReadResult(
            chat=DialogHandle(
                dialog_ref="tg://dialog/user/1",
                id=1,
                name="Andrei",
                type="user",
                username="targetdaddy",
                resolved_from="@targetdaddy",
            ),
            messages=[],
            message_count=0,
        )

        with patch("telegram_mcp.runtime.get_tg", AsyncMock(return_value=wrapper)):
            _run(
                server.read_recent_dialog(
                    chat="@targetdaddy",
                    include_sender_name=False,
                )
            )

        wrapper.read_recent_dialog.assert_awaited_once_with(
            chat="@targetdaddy",
            limit=20,
            offset_id=0,
            include_voice_transcription=False,
            max_voice_transcriptions=None,
            include_sender_name=False,
        )

    def test_telegram_export_members_runs_without_extra_pii_acknowledgement(self) -> None:
        wrapper = AsyncMock()
        wrapper.resolve_dialog.return_value = DialogHandle(
            dialog_ref="tg://dialog/channel/10",
            id=10,
            name="Target",
            type="channel",
            username="targetdaddy",
            resolved_from="@targetdaddy",
        )
        wrapper.get_participants.return_value = ([Participant(id=1, first_name="Ada", username="ada")], 1)

        with patch("telegram_mcp.runtime.get_tg", AsyncMock(return_value=wrapper)):
            result = _run(telegram_export_members(chat="@targetdaddy"))

        self.assertEqual(result.total, 1)
        self.assertEqual(result.participants[0].username, "ada")
        wrapper.get_participants.assert_awaited_once_with(chat="tg://dialog/channel/10", limit=200)

    def test_search_dialog_messages_returns_dialog_read_result(self):
        wrapper = AsyncMock()
        wrapper.search_dialog_messages.return_value = DialogReadResult(
            chat=DialogHandle(
                dialog_ref="tg://dialog/user/1",
                id=1,
                name="Andrei",
                type="user",
                username="targetdaddy",
                resolved_from="@targetdaddy",
            ),
            messages=[],
            message_count=0,
        )

        with patch("telegram_mcp.runtime.get_tg", AsyncMock(return_value=wrapper)):
            result = _run(
                server.search_dialog_messages(
                    chat="@targetdaddy",
                    query="hello",
                    limit=5,
                )
            )

        self.assertEqual(result.chat.username, "targetdaddy")
        wrapper.search_dialog_messages.assert_awaited_once_with(
            chat="@targetdaddy",
            query="hello",
            limit=5,
            include_sender_name=False,
        )

    def test_telegram_read_uses_fast_context_by_default(self):
        wrapper = AsyncMock()
        wrapper.collect_dialog_context.return_value = DialogContextResult(
            chat=DialogHandle(
                dialog_ref="tg://dialog/user/1",
                id=1,
                name="Andrei",
                type="user",
                username="targetdaddy",
                resolved_from="@targetdaddy",
            ),
            messages=[],
            message_count=0,
        )

        with patch("telegram_mcp.runtime.get_tg", AsyncMock(return_value=wrapper)):
            result = _run(server.telegram_read(chat="@targetdaddy"))

        self.assertEqual(result.chat.username, "targetdaddy")
        wrapper.collect_dialog_context.assert_awaited_once_with(
            chat="@targetdaddy",
            mode="fast",
            recent_limit=20,
            include_pinned=False,
            include_voice_transcription=False,
        )

    def test_telegram_search_uses_fast_sender_defaults(self):
        wrapper = AsyncMock()
        wrapper.search_dialog_messages.return_value = DialogReadResult(
            chat=DialogHandle(
                dialog_ref="tg://dialog/user/1",
                id=1,
                name="Andrei",
                type="user",
                username="targetdaddy",
                resolved_from="@targetdaddy",
            ),
            messages=[],
            message_count=0,
        )

        with patch("telegram_mcp.runtime.get_tg", AsyncMock(return_value=wrapper)):
            _run(server.telegram_search(chat="@targetdaddy", query="hello", limit=5))

        wrapper.search_dialog_messages.assert_awaited_once_with(
            chat="@targetdaddy",
            query="hello",
            limit=5,
            include_sender_name=False,
        )

    def test_telegram_prepare_reply_is_preview_only(self):
        wrapper = AsyncMock()
        wrapper.prepare_dialog_reply.return_value = DialogReplyPreparation(
            chat=DialogHandle(
                dialog_ref="tg://dialog/user/1",
                id=1,
                name="Andrei",
                type="user",
                username="targetdaddy",
                resolved_from="@targetdaddy",
            ),
            goal="reply",
            context=DialogContextResult(
                chat=DialogHandle(
                    dialog_ref="tg://dialog/user/1",
                    id=1,
                    name="Andrei",
                    type="user",
                    username="targetdaddy",
                    resolved_from="@targetdaddy",
                ),
                messages=[],
                message_count=0,
            ),
            send_tool="send_dialog_message",
            send_args_preview={"chat": "tg://dialog/user/1", "text": ""},
        )

        with patch("telegram_mcp.runtime.get_tg", AsyncMock(return_value=wrapper)):
            result = _run(server.telegram_prepare_reply(chat="@targetdaddy", goal="reply"))

        self.assertTrue(result.preview_only)
        wrapper.prepare_dialog_reply.assert_awaited_once_with(
            chat="@targetdaddy",
            goal="reply",
            reply_to_message_id=None,
            context_limit=20,
            mode="fast",
            draft_text=None,
        )

    def test_collect_dialog_context_uses_facade_method(self):
        wrapper = AsyncMock()
        wrapper.collect_dialog_context.return_value = DialogContextResult(
            chat=DialogHandle(
                dialog_ref="tg://dialog/user/1",
                id=1,
                name="Andrei",
                type="user",
                username="targetdaddy",
                resolved_from="@targetdaddy",
            ),
            messages=[],
            message_count=0,
        )

        with patch("telegram_mcp.runtime.get_tg", AsyncMock(return_value=wrapper)):
            result = _run(
                server.collect_dialog_context(
                    chat="@targetdaddy",
                    mode="fast",
                    recent_limit=10,
                    include_pinned=False,
                )
            )

        self.assertEqual(result.collection_mode, "fast")
        wrapper.collect_dialog_context.assert_awaited_once_with(
            chat="@targetdaddy",
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
                username="targetdaddy",
                resolved_from="@targetdaddy",
            ),
            messages=[],
            message_count=0,
        )

        with patch("telegram_mcp.runtime.get_tg", AsyncMock(return_value=wrapper)):
            result = _run(server.collect_context(chat="@targetdaddy", recent_limit=10))

        self.assertEqual(result.chat.username, "targetdaddy")
        wrapper.collect_dialog_context.assert_awaited_once_with(
            chat="@targetdaddy",
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

    def test_prepare_dialog_reply_uses_facade_method(self):
        wrapper = AsyncMock()
        context = DialogContextResult(
            chat=DialogHandle(
                dialog_ref="tg://dialog/user/1",
                id=1,
                name="Andrei",
                type="user",
                username="targetdaddy",
                resolved_from="@targetdaddy",
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
                    chat="@targetdaddy",
                    goal="reply",
                    draft_text="hello",
                )
            )

        self.assertTrue(result.preview_only)
        wrapper.prepare_dialog_reply.assert_awaited_once_with(
            chat="@targetdaddy",
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
                username="targetdaddy",
                resolved_from="@targetdaddy",
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
            result = _run(server.draft_reply(chat="@targetdaddy", goal="reply"))

        self.assertTrue(result.preview_only)
        wrapper.prepare_dialog_reply.assert_awaited_once_with(
            chat="@targetdaddy",
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
                username="targetdaddy",
                resolved_from="@targetdaddy",
            ),
            text="hello",
            send_tool="send_dialog_message",
            send_args_preview={"chat": "tg://dialog/user/1", "text": "hello"},
        )

        with patch("telegram_mcp.runtime.get_tg", AsyncMock(return_value=wrapper)):
            result = _run(
                server.prepare_send_message(chat="@targetdaddy", text="hello")
            )

        self.assertTrue(result.preview_only)
        wrapper.prepare_send_message.assert_awaited_once_with(
            chat="@targetdaddy",
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
                username="targetdaddy",
                resolved_from="@targetdaddy",
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
                    chat="@targetdaddy",
                    message_id=3,
                    text="pong",
                )
            )

        self.assertTrue(result.preview_only)
        wrapper.prepare_reply_message.assert_awaited_once_with(
            chat="@targetdaddy",
            message_id=3,
            text="pong",
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
            result = _run(
                server.send_dialog_message(
                    chat="@targetdaddy",
                    text="hello",
                    confirmation_token="token",
                )
            )

        self.assertEqual(result.text, "hello")
        wrapper.send_dialog_message.assert_awaited_once_with(
            chat="@targetdaddy",
            text="hello",
            parse_mode="md",
            confirmation_token="token",
        )

    def test_telegram_confirmed_send_routes_to_send_or_reply(self):
        wrapper = AsyncMock()
        send_result = MessageInfo(
            id=7,
            chat_id=1,
            date=datetime(2026, 4, 17, tzinfo=timezone.utc),
            text="hello",
            is_outgoing=True,
        )
        reply_result = MessageInfo(
            id=8,
            chat_id=1,
            date=datetime(2026, 4, 17, tzinfo=timezone.utc),
            text="pong",
            reply_to_msg_id=3,
            is_outgoing=True,
        )
        wrapper._commit_confirmed_send = AsyncMock(side_effect=[send_result, reply_result])

        with patch("telegram_mcp.runtime.get_tg", AsyncMock(return_value=wrapper)):
            _run(
                server.telegram_confirmed_send(
                    chat="tg://dialog/user/1",
                    text="hello",
                    confirmation_token="send-token",
                )
            )
            _run(
                server.telegram_confirmed_send(
                    chat="tg://dialog/user/1",
                    message_id=3,
                    text="pong",
                    confirmation_token="reply-token",
                )
            )

        assert wrapper._commit_confirmed_send.await_count == 2
        wrapper._commit_confirmed_send.assert_any_await(
            preview_id=None,
            confirmation_token="send-token",
            chat="tg://dialog/user/1",
            text="hello",
            parse_mode="md",
            message_id=None,
        )
        wrapper._commit_confirmed_send.assert_any_await(
            preview_id=None,
            confirmation_token="reply-token",
            chat="tg://dialog/user/1",
            text="pong",
            parse_mode="md",
            message_id=3,
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
                    chat="@targetdaddy",
                    message_id=3,
                    text="pong",
                    confirmation_token="token",
                )
            )

        self.assertEqual(result.reply_to_msg_id, 3)
        wrapper.reply_in_dialog.assert_awaited_once_with(
            chat="@targetdaddy",
            message_id=3,
            text="pong",
            parse_mode="md",
            confirmation_token="token",
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
                    chat="@targetdaddy",
                    message_id=3,
                    text="pong",
                    confirmation_token="token",
                )
            )

        self.assertEqual(result.reply_to_msg_id, 3)
        wrapper.reply_in_dialog.assert_awaited_once_with(
            chat="@targetdaddy",
            message_id=3,
            text="pong",
            parse_mode="md",
            confirmation_token="token",
        )
