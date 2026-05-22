import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from telegram_mcp import server
from telegram_mcp.types import (
    ChatInfo,
    DialogHandle,
    DialogSliceResult,
    MediaBatchResult,
    MediaInspectionManifest,
    MediaInspectionManifestItem,
    MessageInfo,
    MessagesResult,
    UserInfo,
)


def _run(awaitable):
    import asyncio

    return asyncio.run(awaitable)


class ServerOutputTests(unittest.TestCase):
    def test_get_me_returns_structured_user_info(self):
        wrapper = AsyncMock()
        wrapper.get_me.return_value = UserInfo(
            id=1,
            first_name="Sereja",
            username="example",
        )

        with patch("telegram_mcp.runtime.get_tg", AsyncMock(return_value=wrapper)):
            result = _run(server.get_me())

        self.assertIsInstance(result, UserInfo)
        self.assertEqual(result.username, "example")

    def test_list_messages_returns_messages_result(self):
        wrapper = AsyncMock()
        wrapper.read_dialog_slice.return_value = DialogSliceResult(
            chat=ChatInfo(id=11, name="Chat", type="user"),
            messages=[
                MessageInfo(
                    id=7,
                    chat_id=11,
                    date=datetime(2026, 3, 14, tzinfo=timezone.utc),
                    text="hello",
                )
            ],
            voice_transcription_status="disabled",
            truncated=True,
            truncated_reason="message_limit",
        )

        with patch("telegram_mcp.runtime.get_tg", AsyncMock(return_value=wrapper)):
            result = _run(server.list_messages(chat=1))

        self.assertIsInstance(result, MessagesResult)
        self.assertEqual(result.messages[0].text, "hello")
        self.assertEqual(result.voice_transcription_status, "disabled")
        self.assertTrue(result.truncated)
        self.assertEqual(result.truncated_reason, "message_limit")

    def test_search_messages_returns_truncation_metadata(self):
        wrapper = AsyncMock()
        wrapper._search_messages_with_caps.return_value = SimpleNamespace(
            messages=[],
            sender_resolution_count=0,
            truncated=True,
            truncated_reason="char_limit",
        )

        with patch("telegram_mcp.runtime.get_tg", AsyncMock(return_value=wrapper)):
            result = _run(server.search_messages(query="hello", limit=200))

        self.assertIsInstance(result, MessagesResult)
        self.assertTrue(result.truncated)
        self.assertEqual(result.truncated_reason, "char_limit")
        wrapper._search_messages_with_caps.assert_awaited_once_with(
            query="hello",
            chat=None,
            limit=200,
            include_sender_name=True,
        )

    def test_download_media_batch_returns_structured_batch_result(self):
        wrapper = AsyncMock()
        wrapper.download_media_batch.return_value = MediaBatchResult(
            chat_id=11,
            requested_count=2,
            success_count=0,
            failed_count=2,
            items=[],
        )

        with patch("telegram_mcp.runtime.get_tg", AsyncMock(return_value=wrapper)):
            result = _run(server.download_media_batch(chat=1, message_ids=[7, 8]))

        self.assertIsInstance(result, MediaBatchResult)
        wrapper.download_media_batch.assert_awaited_once_with(
            chat=1,
            message_ids=[7, 8],
            concurrency=2,
        )

    def test_download_dialog_media_delegates_to_batch_download(self):
        wrapper = AsyncMock()
        wrapper.download_media_batch.return_value = MediaBatchResult(
            chat_id=11,
            requested_count=1,
            success_count=1,
            failed_count=0,
            items=[],
        )

        with patch("telegram_mcp.runtime.get_tg", AsyncMock(return_value=wrapper)):
            result = _run(server.download_dialog_media(chat=1, message_ids=[7]))

        self.assertIsInstance(result, MediaBatchResult)
        wrapper.download_media_batch.assert_awaited_once_with(
            chat=1,
            message_ids=[7],
            concurrency=2,
        )

    def test_prepare_media_inspection_manifest_returns_structured_manifest(self):
        wrapper = AsyncMock()
        wrapper.prepare_media_inspection_manifest.return_value = MediaInspectionManifest(
            chat=DialogHandle(
                dialog_ref="tg://dialog/user/11",
                id=11,
                name="Chat",
                type="user",
                username=None,
                resolved_from="1",
                match_confidence=1.0,
            ),
            requested_limit=10,
            message_count=1,
            media_count=1,
            items=[
                MediaInspectionManifestItem(
                    message_id=7,
                    chat_id=11,
                    date=datetime(2026, 3, 14, tzinfo=timezone.utc),
                    caption="caption",
                    media_type="photo",
                )
            ],
        )

        with patch("telegram_mcp.runtime.get_tg", AsyncMock(return_value=wrapper)):
            result = _run(server.prepare_media_inspection_manifest(chat=1, limit=10))

        self.assertIsInstance(result, MediaInspectionManifest)
        self.assertEqual(result.items[0].message_id, 7)
        wrapper.prepare_media_inspection_manifest.assert_awaited_once_with(
            chat=1,
            limit=10,
            offset_id=0,
            date_from=None,
            date_to=None,
        )

    def test_get_me_raises_real_errors(self):
        with patch(
            "telegram_mcp.runtime.get_tg",
            AsyncMock(side_effect=RuntimeError("boom")),
        ):
            with self.assertRaises(RuntimeError):
                _run(server.get_me())
