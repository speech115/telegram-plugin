import asyncio
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from telethon.tl.types import Channel, MessageReactions, MessagePeerReaction, PeerUser, ReactionCount, ReactionEmoji

from telegram_mcp.client import TelegramWrapper
from telegram_mcp.config import Settings
from telegram_mcp.errors import ToolContractError


class DummyTelegramClient:
    def __init__(self, *_args, **_kwargs):
        self.transcribe_calls = []
        self.get_entity_calls = []
        self.get_input_entity_calls = []
        self.send_message_calls = []

    async def connect(self):
        return None

    async def is_user_authorized(self):
        return True

    async def get_me(self):
        return SimpleNamespace(
            id=42,
            first_name="Test",
            last_name="",
            username="me",
            phone=None,
            bot=False,
        )

    def is_connected(self):
        return True

    async def disconnect(self):
        return None

    async def get_input_entity(self, entity):
        self.get_input_entity_calls.append(entity)
        return entity

    async def get_entity(self, chat):
        self.get_entity_calls.append(chat)
        if isinstance(chat, str):
            normalized = chat.strip().lstrip("@").lower()
            return SimpleNamespace(id=1, username=normalized, photo=None)
        return SimpleNamespace(id=chat, username="targetdaddy", photo=None)

    async def iter_messages(self, *_args, **_kwargs):
        yield DummyMessage()

    async def send_message(self, entity, text, reply_to=None, parse_mode=None):
        self.send_message_calls.append(
            {
                "entity": entity,
                "text": text,
                "reply_to": reply_to,
                "parse_mode": parse_mode,
            }
        )
        return SimpleNamespace(
            id=901,
            chat_id=getattr(entity, "id", 1),
            sender_id=777,
            date=datetime(2026, 4, 17, tzinfo=timezone.utc),
            text=text,
            edit_date=None,
        )

    async def __call__(self, request):
        self.transcribe_calls.append(request)
        return SimpleNamespace(text="text", pending=False)


class WriteToolsTelegramClient(DummyTelegramClient):
    async def send_message(self, entity, text, reply_to=None, parse_mode=None, buttons=None):
        self.send_message_calls.append(
            {
                "entity": entity,
                "text": text,
                "reply_to": reply_to,
                "parse_mode": parse_mode,
                "buttons": buttons,
            }
        )
        return SimpleNamespace(
            id=901,
            chat_id=getattr(entity, "id", 1),
            sender_id=777,
            date=datetime(2026, 4, 17, tzinfo=timezone.utc),
            text=text,
            edit_date=None,
        )

    async def forward_messages(self, to_entity, message_ids, from_entity):
        return [
            SimpleNamespace(
                id=message_id,
                chat_id=getattr(to_entity, "id", 1),
                sender_id=777,
                date=datetime(2026, 4, 17, tzinfo=timezone.utc),
                text=f"forwarded {message_id}",
                edit_date=None,
            )
            for message_id in message_ids
        ]


class DownloadTelegramClient(DummyTelegramClient):
    async def get_messages(self, *_args, **_kwargs):
        return DummyMessage()

    async def download_media(self, _message, file):
        target = Path(file) / "new.oga"
        target.write_bytes(b"new")
        return str(target)


class BatchDownloadMessage:
    def __init__(self, *, message_id: int, has_media: bool = True):
        self.id = message_id
        self.chat_id = 11
        self.sender_id = None
        self.date = datetime(2026, 3, 14, tzinfo=timezone.utc)
        self.text = ""
        self.reply_to = None
        self.out = False
        self.media = object() if has_media else None
        self.views = None
        self.forwards = None
        self.edit_date = None
        self.voice = False
        self.video_note = False
        self.document = SimpleNamespace(
            id=1000 + message_id,
            dc_id=4,
            size=10 + message_id,
            mime_type="audio/ogg",
            attributes=[],
        )
        self.photo = None
        self.sticker = None
        self.gif = None
        self.video = False
        self.audio = True


class BatchDownloadTelegramClient(DummyTelegramClient):
    def __init__(self, *_args, **_kwargs):
        super().__init__(*_args, **_kwargs)
        self.get_messages_calls = []
        self.download_media_calls = []
        self.active_downloads = 0
        self.max_active_downloads = 0
        self._messages = {
            7: BatchDownloadMessage(message_id=7),
            8: BatchDownloadMessage(message_id=8),
            9: BatchDownloadMessage(message_id=9, has_media=False),
            10: BatchDownloadMessage(message_id=10),
            11: BatchDownloadMessage(message_id=11),
        }

    async def get_messages(self, _entity, ids):
        self.get_messages_calls.append(list(ids))
        return [self._messages.get(message_id) for message_id in ids]

    async def download_media(self, message, file):
        self.active_downloads += 1
        self.max_active_downloads = max(self.max_active_downloads, self.active_downloads)
        try:
            await asyncio.sleep(0.01)
            self.download_media_calls.append(message.id)
            if message.id == 8:
                raise RuntimeError("download failed")
            target = Path(file) / f"{message.id}.oga"
            target.write_bytes(b"new")
            return str(target)
        finally:
            self.active_downloads -= 1


class ManifestTelegramClient(DummyTelegramClient):
    def __init__(self, *_args, **_kwargs):
        super().__init__(*_args, **_kwargs)
        self.get_messages_calls = []

    async def iter_messages(self, *_args, **_kwargs):
        yield BatchDownloadMessage(message_id=7)
        yield BatchDownloadMessage(message_id=9, has_media=False)

    async def get_messages(self, _entity, ids):
        self.get_messages_calls.append(list(ids))
        messages = []
        for message_id in ids:
            if message_id != 7:
                continue
            message = BatchDownloadMessage(message_id=message_id)
            message.document.attributes = [DocumentAttributeAudio()]
            messages.append(message)
        return messages


class ContactTelegramClient(DummyTelegramClient):
    def __init__(self, *_args, **_kwargs):
        super().__init__(*_args, **_kwargs)
        self.requests = []

    async def __call__(self, request):
        self.requests.append(request)
        request_name = type(request).__name__
        if request_name == "GetContactsRequest":
            return SimpleNamespace(
                users=[
                    SimpleNamespace(
                        id=101,
                        first_name="Ada",
                        last_name="Lovelace",
                        username="ada",
                        phone="+100",
                        mutual_contact=True,
                    )
                ]
            )
        if request_name == "ImportContactsRequest":
            return SimpleNamespace(
                users=[
                    SimpleNamespace(
                        id=102,
                        first_name="Grace",
                        last_name="Hopper",
                        username="grace",
                        phone="+200",
                    )
                ],
                imported=[object()],
            )
        return await super().__call__(request)


class StoryLinkTelegramClient(DummyTelegramClient):
    def __init__(self, *_args, **_kwargs):
        super().__init__(*_args, **_kwargs)
        self.requests = []

    async def __call__(self, request):
        self.requests.append(request)
        if type(request).__name__ == "ExportStoryLinkRequest":
            return SimpleNamespace(link="https://t.me/story")
        return await super().__call__(request)


class SlowConnectTelegramClient(DummyTelegramClient):
    async def connect(self):
        await asyncio.sleep(1)


class UnauthorizedTelegramClient(DummyTelegramClient):
    async def is_user_authorized(self):
        return False


class ReconnectTelegramClient(DummyTelegramClient):
    def __init__(self, *_args, **_kwargs):
        super().__init__(*_args, **_kwargs)
        self.connected = False
        self.connect_calls = 0

    def is_connected(self):
        return self.connected

    async def connect(self):
        self.connect_calls += 1
        await asyncio.sleep(0.01)
        self.connected = True


class DummyMessage:
    id = 7
    chat_id = 11
    sender_id = None
    date = datetime(2026, 3, 14, tzinfo=timezone.utc)
    text = ""
    reply_to = None
    out = False
    media = object()
    views = None
    forwards = None
    edit_date = None
    voice = True
    video_note = False
    document = None
    photo = None
    sticker = None
    gif = None
    video = False
    audio = False

    async def get_sender(self):
        return None


class DocumentAttributeAudio:
    def __init__(self, *, voice: bool = False, duration: int | None = None):
        self.voice = voice
        self.duration = duration


class DocumentVoiceDummyMessage(DummyMessage):
    voice = False
    document = SimpleNamespace(
        attributes=[DocumentAttributeAudio(voice=True, duration=20)]
    )


class DocumentVoiceTelegramClient(DummyTelegramClient):
    async def iter_messages(self, *_args, **_kwargs):
        yield DocumentVoiceDummyMessage()


class DurationDummyMessage(DummyMessage):
    document = SimpleNamespace(attributes=[SimpleNamespace(duration=37)])
    voice = True


class DurationTelegramClient(DummyTelegramClient):
    async def iter_messages(self, *_args, **_kwargs):
        yield DurationDummyMessage()


class DatedDummyMessage(DummyMessage):
    def __init__(self, *, message_id: int, when: datetime):
        self.id = message_id
        self.date = when


class DateRangeTelegramClient(DummyTelegramClient):
    def __init__(self, *_args, **_kwargs):
        super().__init__(*_args, **_kwargs)
        self.iter_messages_kwargs = []

    async def iter_messages(self, *_args, **kwargs):
        self.iter_messages_kwargs.append(kwargs)
        yield DatedDummyMessage(
            message_id=101,
            when=datetime(2026, 4, 17, 10, 0, tzinfo=timezone.utc),
        )
        yield DatedDummyMessage(
            message_id=102,
            when=datetime(2026, 4, 16, 11, 0, tzinfo=timezone.utc),
        )
        yield DatedDummyMessage(
            message_id=103,
            when=datetime(2026, 4, 15, 9, 0, tzinfo=timezone.utc),
        )


class CursorTelegramClient(DummyTelegramClient):
    def __init__(self, *_args, **_kwargs):
        super().__init__(*_args, **_kwargs)
        self.iter_messages_kwargs = []
        self._messages = [
            DatedDummyMessage(
                message_id=301,
                when=datetime(2026, 4, 16, 12, 0, tzinfo=timezone.utc),
            ),
            DatedDummyMessage(
                message_id=302,
                when=datetime(2026, 4, 16, 11, 0, tzinfo=timezone.utc),
            ),
            DatedDummyMessage(
                message_id=303,
                when=datetime(2026, 4, 16, 10, 0, tzinfo=timezone.utc),
            ),
        ]

    async def iter_messages(self, *_args, **kwargs):
        self.iter_messages_kwargs.append(kwargs)
        offset_id = kwargs.get("offset_id", 0)
        for message in self._messages:
            if offset_id and message.id >= offset_id:
                continue
            yield message


class SlowReadTelegramClient(DummyTelegramClient):
    def __init__(self, *_args, **_kwargs):
        super().__init__(*_args, **_kwargs)
        self.iter_message_calls = 0
        self.iter_started = asyncio.Event()
        self.release_iter = asyncio.Event()

    async def iter_messages(self, *_args, **_kwargs):
        self.iter_message_calls += 1
        self.iter_started.set()
        await self.release_iter.wait()
        yield DummyMessage()


class SlowTranscriptionTelegramClient(DummyTelegramClient):
    def __init__(self, *_args, **_kwargs):
        super().__init__(*_args, **_kwargs)
        self.transcribe_started = asyncio.Event()
        self.release_transcribe = asyncio.Event()

    async def __call__(self, request):
        self.transcribe_calls.append(request)
        self.transcribe_started.set()
        await self.release_transcribe.wait()
        return SimpleNamespace(text="text", pending=False)


class PendingVoiceTelegramClient(DummyTelegramClient):
    async def __call__(self, request):
        self.transcribe_calls.append(request)
        return SimpleNamespace(text="", pending=True)


class FailingTranscriptionTelegramClient(DummyTelegramClient):
    async def __call__(self, request):
        self.transcribe_calls.append(request)
        raise RuntimeError("telegram refused transcription")


class TimeoutTranscriptionTelegramClient(DocumentVoiceTelegramClient):
    async def __call__(self, request):
        self.transcribe_calls.append(request)
        raise ToolContractError("operation_timeout", "transcribe timed out")


class SenderCacheMessage(DummyMessage):
    media = None
    voice = False

    def __init__(self, *, message_id: int, sender_id: int):
        self.id = message_id
        self.sender_id = sender_id
        self.sender = None
        self.get_sender_calls = 0

    async def get_sender(self):
        self.get_sender_calls += 1
        return SimpleNamespace(id=self.sender_id)


class SenderCacheTelegramClient(DummyTelegramClient):
    def __init__(self, *_args, **_kwargs):
        super().__init__(*_args, **_kwargs)
        self._messages = [
            SenderCacheMessage(message_id=1, sender_id=501),
            SenderCacheMessage(message_id=2, sender_id=501),
            SenderCacheMessage(message_id=3, sender_id=777),
        ]

    async def iter_messages(self, *_args, **_kwargs):
        for message in self._messages:
            yield message


class FullContextMessage(SenderCacheMessage):
    media = object()
    voice = True

    def __init__(self, *, message_id: int, sender_id: int):
        super().__init__(message_id=message_id, sender_id=sender_id)
        self.chat_id = 11
        self.date = datetime(2026, 4, 17, tzinfo=timezone.utc)
        self.text = f"voice {message_id}"
        self.reply_to = None
        self.out = False
        self.views = None
        self.forwards = None
        self.edit_date = None
        self.video_note = False
        self.document = None
        self.photo = None
        self.sticker = None
        self.gif = None
        self.video = False
        self.audio = False


class FullContextTelegramClient(DummyTelegramClient):
    def __init__(self, *_args, **_kwargs):
        super().__init__(*_args, **_kwargs)
        self._messages = [
            FullContextMessage(message_id=1, sender_id=501),
            FullContextMessage(message_id=2, sender_id=501),
            FullContextMessage(message_id=3, sender_id=777),
        ]

    async def iter_messages(self, *_args, **_kwargs):
        for message in self._messages:
            yield message


class OutputCapMessage(DummyMessage):
    def __init__(self, *, message_id: int, text: str, has_media: bool = False):
        self.id = message_id
        self.chat_id = 11
        self.sender_id = None
        self.date = datetime(2026, 4, 17, tzinfo=timezone.utc)
        self.text = text
        self.reply_to = None
        self.out = False
        self.media = object() if has_media else None
        self.views = None
        self.forwards = None
        self.edit_date = None
        self.voice = False
        self.video_note = False
        self.document = None
        self.photo = None
        self.sticker = None
        self.gif = None
        self.video = False
        self.audio = False


class OutputCapTelegramClient(DummyTelegramClient):
    def __init__(self, *_args, **_kwargs):
        super().__init__(*_args, **_kwargs)
        self.iter_messages_kwargs = []
        self._messages = [
            OutputCapMessage(message_id=1, text="one", has_media=True),
            OutputCapMessage(message_id=2, text="two", has_media=True),
            OutputCapMessage(message_id=3, text="three"),
        ]

    async def iter_messages(self, *_args, **kwargs):
        self.iter_messages_kwargs.append(kwargs)
        for message in self._messages:
            yield message


class SentMediaSearchTelegramClient(DummyTelegramClient):
    def __init__(self, *_args, **_kwargs):
        super().__init__(*_args, **_kwargs)
        self.iter_dialogs_kwargs = []
        self.iter_messages_args = []
        self.iter_messages_kwargs = []

    async def iter_dialogs(self, **kwargs):
        self.iter_dialogs_kwargs.append(kwargs)
        yield SimpleNamespace(entity=SimpleNamespace(id=501, username="chat1"))

    async def iter_messages(self, *args, **kwargs):
        self.iter_messages_args.append(args)
        self.iter_messages_kwargs.append(kwargs)
        message = OutputCapMessage(message_id=91, text="sent media", has_media=True)
        message.out = True
        message.photo = object()
        yield message


class ThreadForumTelegramClient(DummyTelegramClient):
    def __init__(self, *_args, **_kwargs):
        super().__init__(*_args, **_kwargs)
        self.requests = []
        self.iter_messages_kwargs = []

    async def __call__(self, request):
        self.requests.append(request)
        request_name = type(request).__name__
        if request_name == "GetForumTopicsRequest":
            return SimpleNamespace(
                topics=[
                    SimpleNamespace(
                        id=11,
                        title="Announcements",
                        top_message=101,
                        date=datetime(2026, 4, 17, tzinfo=timezone.utc),
                        unread_count=2,
                        unread_mentions_count=1,
                        unread_reactions_count=3,
                        closed=False,
                        pinned=True,
                        hidden=False,
                        icon_color=0x6FB9F0,
                        icon_emoji_id=123,
                    )
                ],
                count=1,
                order_by_create_date=True,
            )
        if request_name == "GetForumTopicsByIDRequest":
            return SimpleNamespace(
                topics=[SimpleNamespace(id=12, title="Support", top_message=102)]
            )
        if request_name == "GetDiscussionMessageRequest":
            return SimpleNamespace(
                messages=[
                    OutputCapMessage(message_id=501, text="discussion", has_media=False)
                ]
            )
        return await super().__call__(request)

    async def iter_messages(self, *_args, **kwargs):
        self.iter_messages_kwargs.append(kwargs)
        yield OutputCapMessage(message_id=601, text="reply 1", has_media=False)
        yield OutputCapMessage(message_id=600, text="reply 2", has_media=False)


class ReactionAnalyticsTelegramClient(DummyTelegramClient):
    def __init__(self, *_args, **_kwargs):
        super().__init__(*_args, **_kwargs)
        self.requests = []

    async def get_messages(self, _entity, ids):
        message = OutputCapMessage(message_id=ids, text="reacted", has_media=False)
        message.reactions = MessageReactions(
            results=[
                ReactionCount(reaction=ReactionEmoji("👍"), count=3),
            ],
            can_see_list=True,
        )
        return message

    async def __call__(self, request):
        self.requests.append(request)
        request_name = type(request).__name__
        if request_name == "GetMessageReactionsListRequest":
            return SimpleNamespace(
                reactions=[
                    MessagePeerReaction(
                        peer_id=PeerUser(777),
                        date=datetime(2026, 4, 17, tzinfo=timezone.utc),
                        reaction=ReactionEmoji("👍"),
                        unread=True,
                    )
                ],
                next_offset="next",
            )
        if request_name == "GetUnreadReactionsRequest":
            return SimpleNamespace(
                messages=[
                    OutputCapMessage(message_id=701, text="unread reaction", has_media=False)
                ]
            )
        return await super().__call__(request)


class NonUserDialogTelegramClient(DummyTelegramClient):
    async def get_entity(self, chat):
        self.get_entity_calls.append(chat)
        if chat == "@channelslug":
            return SimpleNamespace(
                id=777,
                username="channelslug",
                photo=None,
                _forced_type="channel",
                _forced_name="Channel Slug",
            )
        if chat == 777:
            raise AssertionError("numeric channel fallback used")
        return await super().get_entity(chat)


class ClientTests(unittest.TestCase):
    def test_get_message_link_uses_public_username_when_available(self):
        settings = Settings(api_id=1, api_hash="hash")

        with patch("telegram_mcp.client.TelegramClient", DummyTelegramClient):
            wrapper = TelegramWrapper(settings)

        link = _run(wrapper.get_message_link(chat="@targetdaddy", message_id=42))

        self.assertEqual(link, "https://t.me/targetdaddy/42")

    def test_get_message_link_uses_private_c_link_without_username(self):
        settings = Settings(api_id=1, api_hash="hash")

        with patch("telegram_mcp.client.TelegramClient", DummyTelegramClient):
            wrapper = TelegramWrapper(settings)

        wrapper.client.get_entity = AsyncMock(
            return_value=SimpleNamespace(id=12345, username=None)
        )

        link = _run(wrapper.get_message_link(chat=12345, message_id=42))

        self.assertEqual(link, "https://t.me/c/12345/42")

    def test_get_message_link_uses_c_link_for_channels_without_username(self):
        settings = Settings(api_id=1, api_hash="hash")

        with patch("telegram_mcp.client.TelegramClient", DummyTelegramClient):
            wrapper = TelegramWrapper(settings)

        wrapper.client.get_entity = AsyncMock(
            return_value=Channel(
                id=98765,
                title="Private Channel",
                photo=None,
                date=None,
                username=None,
            )
        )

        link = _run(wrapper.get_message_link(chat=98765, message_id=42))

        self.assertEqual(link, "https://t.me/c/98765/42")

    def test_connect_timeout_releases_file_session_lock(self):
        settings = Settings(
            api_id=1,
            api_hash="hash",
            connect_timeout_seconds=0.01,
        )
        events: list[str] = []

        class FakeLock:
            def __init__(self, _path):
                events.append("init")

            def acquire(self):
                events.append("acquire")

            def release(self):
                events.append("release")

        with patch("telegram_mcp.client.TelegramClient", SlowConnectTelegramClient):
            with patch("telegram_mcp.client.FileSessionLock", FakeLock):
                wrapper = TelegramWrapper(settings)
                with self.assertRaises(RuntimeError):
                    _run(wrapper.connect())

        self.assertEqual(events, ["init", "acquire", "release"])

    def test_connect_auth_failure_releases_file_session_lock(self):
        settings = Settings(api_id=1, api_hash="hash")
        events: list[str] = []

        class FakeLock:
            def __init__(self, _path):
                events.append("init")

            def acquire(self):
                events.append("acquire")

            def release(self):
                events.append("release")

        with patch("telegram_mcp.client.TelegramClient", UnauthorizedTelegramClient):
            with patch("telegram_mcp.client.FileSessionLock", FakeLock):
                wrapper = TelegramWrapper(settings)
                with self.assertRaises(ToolContractError) as ctx:
                    _run(wrapper.connect())

        self.assertEqual(ctx.exception.code, "auth_required")
        self.assertEqual(events, ["init", "acquire", "release"])

    def test_ensure_connected_auth_failure_is_structured(self):
        settings = Settings(api_id=1, api_hash="hash")

        with patch("telegram_mcp.client.TelegramClient", ReconnectTelegramClient):
            wrapper = TelegramWrapper(settings)

        async def unauthorized():
            return False

        wrapper.client.is_user_authorized = unauthorized

        with self.assertRaises(ToolContractError) as ctx:
            _run(wrapper.ensure_connected())

        self.assertEqual(ctx.exception.code, "auth_required")

    def test_concurrent_ensure_connected_uses_single_reconnect(self):
        settings = Settings(api_id=1, api_hash="hash")

        with patch("telegram_mcp.client.TelegramClient", ReconnectTelegramClient):
            wrapper = TelegramWrapper(settings)

        async def run_concurrent_reconnects():
            await asyncio.gather(
                wrapper.ensure_connected(),
                wrapper.ensure_connected(),
            )

        _run(run_concurrent_reconnects())

        self.assertEqual(wrapper.client.connect_calls, 1)

    def test_concurrent_identical_read_calls_share_inflight_work_only(self):
        settings = Settings(api_id=1, api_hash="hash")

        with patch("telegram_mcp.client.TelegramClient", SlowReadTelegramClient):
            wrapper = TelegramWrapper(settings)

        async def run_concurrent_reads():
            first = asyncio.create_task(wrapper.list_messages(chat=1, limit=1))
            await asyncio.wait_for(wrapper.client.iter_started.wait(), timeout=1)
            second = asyncio.create_task(wrapper.list_messages(chat=1, limit=1))
            await asyncio.sleep(0)
            self.assertEqual(wrapper.client.iter_message_calls, 1)
            wrapper.client.release_iter.set()
            first_result, second_result = await asyncio.gather(first, second)
            return first_result, second_result

        first_result, second_result = _run(run_concurrent_reads())

        self.assertEqual([message.id for message in first_result], [7])
        self.assertEqual([message.id for message in second_result], [7])
        self.assertEqual(wrapper.client.iter_message_calls, 1)

        third_result = _run(wrapper.list_messages(chat=1, limit=1))

        self.assertEqual([message.id for message in third_result], [7])
        self.assertEqual(wrapper.client.iter_message_calls, 2)

    def test_internal_search_helper_shares_inflight_work_for_tool_path(self):
        settings = Settings(api_id=1, api_hash="hash")

        with patch("telegram_mcp.client.TelegramClient", SlowReadTelegramClient):
            wrapper = TelegramWrapper(settings)

        async def run_concurrent_searches():
            first = asyncio.create_task(
                wrapper._search_messages_with_caps(query="needle", chat=1, limit=1)
            )
            await asyncio.wait_for(wrapper.client.iter_started.wait(), timeout=1)
            second = asyncio.create_task(
                wrapper._search_messages_with_caps(query="needle", chat=1, limit=1)
            )
            await asyncio.sleep(0)
            self.assertEqual(wrapper.client.iter_message_calls, 1)
            wrapper.client.release_iter.set()
            return await asyncio.gather(first, second)

        first_result, second_result = _run(run_concurrent_searches())

        self.assertEqual([message.id for message in first_result.messages], [7])
        self.assertEqual([message.id for message in second_result.messages], [7])
        self.assertEqual(wrapper.client.iter_message_calls, 1)

    def test_sent_media_search_uses_global_sent_media_filter(self):
        settings = Settings(api_id=1, api_hash="hash")

        with patch("telegram_mcp.client.TelegramClient", SentMediaSearchTelegramClient):
            wrapper = TelegramWrapper(settings)

        result = _run(wrapper.sent_media_search(media_type="photo", limit=3))

        self.assertEqual([message.id for message in result.messages], [91])
        self.assertEqual(wrapper.client.iter_dialogs_kwargs[0]["limit"], 20)
        self.assertEqual(wrapper.client.iter_messages_args[0][0].id, 501)
        kwargs = wrapper.client.iter_messages_kwargs[0]
        self.assertEqual(kwargs["limit"], 4)
        self.assertEqual(kwargs["from_user"], "me")
        self.assertEqual(type(kwargs["filter"]).__name__, "InputMessagesFilterPhotos")

    def test_list_forum_topics_uses_forum_topics_request(self):
        settings = Settings(api_id=1, api_hash="hash")

        with patch("telegram_mcp.client.TelegramClient", ThreadForumTelegramClient):
            wrapper = TelegramWrapper(settings)

        result = _run(wrapper.list_forum_topics(chat="@forum", limit=5, q="ann"))

        self.assertEqual([topic.id for topic in result.topics], [11])
        self.assertEqual(result.topics[0].title, "Announcements")
        self.assertTrue(result.topics[0].pinned)
        request = wrapper.client.requests[0]
        self.assertEqual(type(request).__name__, "GetForumTopicsRequest")
        self.assertEqual(request.limit, 5)
        self.assertEqual(request.q, "ann")

    def test_get_forum_topics_by_id_uses_topic_ids(self):
        settings = Settings(api_id=1, api_hash="hash")

        with patch("telegram_mcp.client.TelegramClient", ThreadForumTelegramClient):
            wrapper = TelegramWrapper(settings)

        result = _run(wrapper.get_forum_topics_by_id(chat="@forum", topic_ids=[12]))

        self.assertEqual([topic.id for topic in result.topics], [12])
        request = wrapper.client.requests[0]
        self.assertEqual(type(request).__name__, "GetForumTopicsByIDRequest")
        self.assertEqual(request.topics, [12])

    def test_get_discussion_message_uses_discussion_request(self):
        settings = Settings(api_id=1, api_hash="hash")

        with patch("telegram_mcp.client.TelegramClient", ThreadForumTelegramClient):
            wrapper = TelegramWrapper(settings)

        result = _run(wrapper.get_discussion_message(chat="@channel", message_id=501))

        self.assertEqual([message.id for message in result.messages], [501])
        request = wrapper.client.requests[0]
        self.assertEqual(type(request).__name__, "GetDiscussionMessageRequest")
        self.assertEqual(request.msg_id, 501)

    def test_get_thread_replies_uses_reply_to_iterator_and_caps(self):
        settings = Settings(api_id=1, api_hash="hash")

        with patch("telegram_mcp.client.TelegramClient", ThreadForumTelegramClient):
            wrapper = TelegramWrapper(settings)

        result = _run(wrapper.get_thread_replies(chat="@forum", message_id=10, limit=1))

        self.assertEqual([message.id for message in result.messages], [601])
        self.assertTrue(result.has_more_before)
        kwargs = wrapper.client.iter_messages_kwargs[0]
        self.assertEqual(kwargs["reply_to"], 10)
        self.assertEqual(kwargs["limit"], 2)

    def test_get_message_reactions_returns_counts_and_visible_peers(self):
        settings = Settings(api_id=1, api_hash="hash")

        with patch("telegram_mcp.client.TelegramClient", ReactionAnalyticsTelegramClient):
            wrapper = TelegramWrapper(settings)

        result = _run(
            wrapper.get_message_reactions(
                chat="@targetdaddy",
                message_id=7,
                limit=5,
                reaction="👍",
            )
        )

        self.assertEqual(result.message_id, 7)
        self.assertEqual(result.counts[0].reaction, "👍")
        self.assertEqual(result.counts[0].count, 3)
        self.assertEqual(result.peers[0].peer_id, 777)
        self.assertEqual(result.peers[0].peer_type, "user")
        self.assertTrue(result.peers[0].unread)
        self.assertEqual(result.next_offset, "next")
        request = wrapper.client.requests[0]
        self.assertEqual(type(request).__name__, "GetMessageReactionsListRequest")
        self.assertEqual(request.id, 7)
        self.assertEqual(request.limit, 5)
        self.assertEqual(request.reaction.emoticon, "👍")

    def test_get_unread_reactions_returns_messages_without_marking_read(self):
        settings = Settings(api_id=1, api_hash="hash")

        with patch("telegram_mcp.client.TelegramClient", ReactionAnalyticsTelegramClient):
            wrapper = TelegramWrapper(settings)

        result = _run(wrapper.get_unread_reactions(chat="@targetdaddy", limit=1, topic_id=10))

        self.assertEqual([message.id for message in result.messages], [701])
        self.assertEqual(result.next_offset_id, 701)
        request = wrapper.client.requests[0]
        self.assertEqual(type(request).__name__, "GetUnreadReactionsRequest")
        self.assertEqual(request.limit, 2)
        self.assertEqual(request.top_msg_id, 10)

    def test_internal_pinned_helper_shares_inflight_work_for_tool_path(self):
        settings = Settings(api_id=1, api_hash="hash")

        with patch("telegram_mcp.client.TelegramClient", SlowReadTelegramClient):
            wrapper = TelegramWrapper(settings)

        async def run_concurrent_pinned_reads():
            first = asyncio.create_task(
                wrapper._get_pinned_messages_with_caps(chat=1, limit=1)
            )
            await asyncio.wait_for(wrapper.client.iter_started.wait(), timeout=1)
            second = asyncio.create_task(
                wrapper._get_pinned_messages_with_caps(chat=1, limit=1)
            )
            await asyncio.sleep(0)
            self.assertEqual(wrapper.client.iter_message_calls, 1)
            wrapper.client.release_iter.set()
            return await asyncio.gather(first, second)

        first_result, second_result = _run(run_concurrent_pinned_reads())

        self.assertEqual([message.id for message in first_result.messages], [7])
        self.assertEqual([message.id for message in second_result.messages], [7])
        self.assertEqual(wrapper.client.iter_message_calls, 1)

    def test_read_inflight_dedupe_does_not_reuse_completed_task(self):
        settings = Settings(api_id=1, api_hash="hash")

        with patch("telegram_mcp.client.TelegramClient", DummyTelegramClient):
            wrapper = TelegramWrapper(settings)

        async def run_sequential_reads():
            calls = 0

            async def factory():
                nonlocal calls
                calls += 1
                return calls

            first = await wrapper._dedupe_read_call(("read", "same"), factory)
            second = await wrapper._dedupe_read_call(("read", "same"), factory)
            return first, second, calls

        first, second, calls = _run(run_sequential_reads())

        self.assertEqual((first, second, calls), (1, 2, 2))

    def test_complete_voice_transcript_cache_reuses_chat_message_result(self):
        settings = Settings(api_id=1, api_hash="hash")

        with patch("telegram_mcp.client.TelegramClient", DocumentVoiceTelegramClient):
            wrapper = TelegramWrapper(settings)

        first = _run(wrapper.transcribe_voice(chat=1, message_id=7))
        second = _run(wrapper.transcribe_voice(chat=1, message_id=7))

        self.assertEqual(first.text, "text")
        self.assertFalse(first.pending)
        self.assertEqual(second.text, "text")
        self.assertFalse(second.pending)
        self.assertEqual(len(wrapper.client.transcribe_calls), 1)

    def test_pending_voice_transcript_is_not_cached(self):
        settings = Settings(api_id=1, api_hash="hash")

        with patch("telegram_mcp.client.TelegramClient", PendingVoiceTelegramClient):
            wrapper = TelegramWrapper(settings)

        first = _run(wrapper.transcribe_voice(chat=1, message_id=7))
        second = _run(wrapper.transcribe_voice(chat=1, message_id=7))

        self.assertTrue(first.pending)
        self.assertTrue(second.pending)
        self.assertEqual(len(wrapper.client.transcribe_calls), 2)

    def test_concurrent_identical_transcribes_share_inflight_request(self):
        settings = Settings(api_id=1, api_hash="hash")

        with patch("telegram_mcp.client.TelegramClient", SlowTranscriptionTelegramClient):
            wrapper = TelegramWrapper(settings)

        async def run_concurrent_transcribes():
            first = asyncio.create_task(wrapper.transcribe_voice(chat=1, message_id=7))
            await asyncio.wait_for(wrapper.client.transcribe_started.wait(), timeout=1)
            second = asyncio.create_task(wrapper.transcribe_voice(chat=1, message_id=7))
            await asyncio.sleep(0)
            self.assertEqual(len(wrapper.client.transcribe_calls), 1)
            wrapper.client.release_transcribe.set()
            return await asyncio.gather(first, second)

        first, second = _run(run_concurrent_transcribes())

        self.assertEqual(first.text, "text")
        self.assertEqual(second.text, "text")
        self.assertEqual(len(wrapper.client.transcribe_calls), 1)

    def test_list_chats_rejects_negative_limit(self):
        settings = Settings(api_id=1, api_hash="hash")

        with patch("telegram_mcp.client.TelegramClient", DummyTelegramClient):
            wrapper = TelegramWrapper(settings)

        async def iter_dialogs_should_not_run(*_args, **_kwargs):
            raise AssertionError("iter_dialogs should not run for invalid limit")
            yield  # pragma: no cover

        wrapper.client.iter_dialogs = iter_dialogs_should_not_run

        with self.assertRaises(ToolContractError) as ctx:
            _run(wrapper.list_chats(limit=-1))

        self.assertEqual(ctx.exception.code, "invalid_pagination")

    def test_resolve_dialog_returns_stable_dialog_ref(self):
        settings = Settings(api_id=1, api_hash="hash")

        with patch("telegram_mcp.client.TelegramClient", DummyTelegramClient):
            wrapper = TelegramWrapper(settings)

        result = _run(wrapper.resolve_dialog("@targetdaddy"))

        self.assertEqual(result.id, 1)
        self.assertEqual(result.username, "targetdaddy")
        self.assertEqual(result.dialog_ref, "tg://dialog/unknown/1")
        self.assertEqual(result.resolved_from, "@targetdaddy")
        self.assertEqual(result.candidate_count, 1)

    def test_read_dialog_by_date_returns_stable_envelope(self):
        settings = Settings(api_id=1, api_hash="hash")

        with patch("telegram_mcp.client.TelegramClient", DateRangeTelegramClient):
            wrapper = TelegramWrapper(settings)

        result = _run(
            wrapper.read_dialog_by_date(
                chat="@targetdaddy",
                date_from="2026-04-16",
                date_to="2026-04-16",
                total_limit=20,
                include_voice_transcription=True,
            )
        )

        self.assertEqual(result.chat.dialog_ref, "tg://dialog/unknown/1")
        self.assertEqual(result.message_count, 1)
        self.assertEqual(result.range.date_from, "2026-04-16")
        self.assertEqual(result.range.date_to, "2026-04-16")
        self.assertEqual(result.data_source, "live_telegram")
        self.assertEqual(result.messages[0].voice_transcription, "text")
        self.assertEqual(result.messages[0].voice_transcription_status, "complete")
        self.assertEqual(result.voice_transcription_status, "complete")
        self.assertEqual(result.omitted_voice_count, 0)
        self.assertEqual(len(wrapper.client.transcribe_calls), 1)

    def test_read_dialog_by_date_can_disable_voice_transcription(self):
        settings = Settings(api_id=1, api_hash="hash")

        with patch("telegram_mcp.client.TelegramClient", DateRangeTelegramClient):
            wrapper = TelegramWrapper(settings)

        result = _run(
            wrapper.read_dialog_by_date(
                chat="@targetdaddy",
                date_from="2026-04-16",
                date_to="2026-04-16",
                total_limit=20,
                include_voice_transcription=False,
            )
        )

        self.assertEqual(result.message_count, 1)
        self.assertIsNone(result.messages[0].voice_transcription)
        self.assertIsNone(result.messages[0].voice_transcription_status)
        self.assertEqual(result.voice_transcription_status, "disabled")
        self.assertEqual(wrapper.client.transcribe_calls, [])

    def test_read_dialog_by_date_reuses_short_dialog_cache(self):
        settings = Settings(api_id=1, api_hash="hash")

        with patch("telegram_mcp.client.TelegramClient", DateRangeTelegramClient):
            wrapper = TelegramWrapper(settings)

        first = _run(
            wrapper.read_dialog_by_date(
                chat=" @TargetDaddy ",
                date_from="2026-04-16",
                date_to="2026-04-16",
                include_voice_transcription=False,
            )
        )
        second = _run(
            wrapper.read_dialog_by_date(
                chat="@targetdaddy",
                date_from="2026-04-16",
                date_to="2026-04-16",
                include_voice_transcription=False,
            )
        )

        self.assertEqual(first.message_count, 1)
        self.assertIs(first, second)
        self.assertEqual(len(wrapper.client.iter_messages_kwargs), 1)

    def test_read_dialog_by_date_accepts_dialog_ref(self):
        settings = Settings(api_id=1, api_hash="hash")

        with patch("telegram_mcp.client.TelegramClient", DateRangeTelegramClient):
            wrapper = TelegramWrapper(settings)

        handle = _run(wrapper.resolve_dialog("@targetdaddy"))
        result = _run(
            wrapper.read_dialog_by_date(
                chat=handle.dialog_ref,
                date_from="2026-04-16",
                date_to="2026-04-16",
            )
        )

        self.assertEqual(result.message_count, 1)

    def test_dialog_read_registers_dialog_ref_and_reuses_input_peer(self):
        settings = Settings(api_id=1, api_hash="hash", dialog_read_cache_ttl_seconds=0)

        with patch("telegram_mcp.client.TelegramClient", NonUserDialogTelegramClient):
            with patch(
                "telegram_mcp.client_chats.get_entity_type",
                lambda entity: getattr(entity, "_forced_type", "unknown"),
            ):
                with patch(
                    "telegram_mcp.client_chats.get_display_name",
                    lambda entity: getattr(entity, "_forced_name", str(entity.id)),
                ):
                    wrapper = TelegramWrapper(settings)
                    first = _run(wrapper.read_recent_dialog(chat="@channelslug", limit=1))
                    second = _run(wrapper.read_recent_dialog(chat=first.chat.dialog_ref, limit=1))

        self.assertEqual(first.chat.dialog_ref, "tg://dialog/channel/777")
        self.assertEqual(second.chat.dialog_ref, first.chat.dialog_ref)
        self.assertEqual(wrapper.client.get_entity_calls, ["@channelslug"])
        self.assertEqual(len(wrapper.client.get_input_entity_calls), 1)

    def test_read_today_dialog_uses_single_day_window(self):
        settings = Settings(api_id=1, api_hash="hash")

        with patch("telegram_mcp.client.TelegramClient", DateRangeTelegramClient):
            wrapper = TelegramWrapper(settings)

        result = _run(
            wrapper.read_today_dialog(
                chat="@targetdaddy",
                day="2026-04-16",
                limit=20,
            )
        )

        self.assertEqual(result.message_count, 1)
        self.assertEqual(result.range.date_from, "2026-04-16")
        self.assertEqual(result.range.date_to, "2026-04-16")

    def test_collect_dialog_context_fast_mode_skips_voice_and_sender_names(self):
        settings = Settings(api_id=1, api_hash="hash")

        with patch("telegram_mcp.client.TelegramClient", SenderCacheTelegramClient):
            wrapper = TelegramWrapper(settings)

        result = _run(
            wrapper.collect_dialog_context(
                chat="@targetdaddy",
                mode="fast",
                recent_limit=3,
                include_pinned=True,
                pinned_limit=1,
            )
        )

        self.assertEqual(result.collection_mode, "fast")
        self.assertFalse(result.include_voice_transcription)
        self.assertEqual(result.sender_resolution_count, 0)
        self.assertEqual(result.pinned_count, 1)
        self.assertEqual(result.voice_transcription_status, "disabled")
        self.assertEqual(result.evidence_message_ids, [1, 2, 3])
        self.assertEqual(wrapper.client.transcribe_calls, [])
        self.assertEqual(
            [message.get_sender_calls for message in wrapper.client._messages],
            [0, 0, 0],
        )

    def test_collect_dialog_context_full_mode_uses_sender_and_voice_budgets(self):
        settings = Settings(api_id=1, api_hash="hash")

        with patch("telegram_mcp.client.TelegramClient", FullContextTelegramClient):
            wrapper = TelegramWrapper(settings)

        result = _run(
            wrapper.collect_dialog_context(
                chat="@targetdaddy",
                mode="full",
                recent_limit=3,
                include_pinned=False,
                max_voice_transcriptions=2,
            )
        )

        self.assertEqual(result.collection_mode, "full")
        self.assertTrue(result.include_voice_transcription)
        self.assertEqual(result.sender_resolution_count, 2)
        self.assertEqual(result.voice_transcription_count, 2)
        self.assertEqual(result.omitted_voice_count, 1)
        self.assertEqual(result.voice_transcription_status, "partial")
        self.assertEqual(len(wrapper.client.transcribe_calls), 2)
        self.assertEqual(
            [message.get_sender_calls for message in wrapper.client._messages],
            [1, 0, 1],
        )

    def test_collect_dialog_context_propagates_truncation_state(self):
        settings = Settings(api_id=1, api_hash="hash", read_max_messages=1)

        with patch("telegram_mcp.client.TelegramClient", OutputCapTelegramClient):
            wrapper = TelegramWrapper(settings)

        result = _run(
            wrapper.collect_dialog_context(
                chat="@targetdaddy",
                recent_limit=10,
                include_pinned=False,
            )
        )

        self.assertTrue(result.truncated)
        self.assertEqual(result.truncated_reason, "message_limit")
        self.assertTrue(result.has_more_before)
        self.assertEqual(result.next_offset_id, 1)

    def test_prepare_dialog_reply_returns_preview_without_sending(self):
        settings = Settings(api_id=1, api_hash="hash")

        with patch("telegram_mcp.client.TelegramClient", DummyTelegramClient):
            wrapper = TelegramWrapper(settings)

        result = _run(
            wrapper.prepare_dialog_reply(
                chat="@targetdaddy",
                goal="ask for the file",
                reply_to_message_id=7,
                draft_text="Can you send the file?",
            )
        )

        self.assertTrue(result.preview_only)
        self.assertEqual(result.send_tool, "telegram_confirmed_send")
        self.assertEqual(result.send_args_preview["chat"], result.chat.dialog_ref)
        self.assertEqual(result.send_args_preview["message_id"], 7)
        self.assertEqual(result.send_args_preview["text"], "Can you send the file?")
        self.assertTrue(result.confirmation_token)
        self.assertEqual(
            result.send_args_preview["confirmation_token"],
            result.confirmation_token,
        )
        self.assertEqual(result.evidence_message_ids, [7])
        self.assertEqual(wrapper.client.send_message_calls, [])

    def test_read_recent_dialog_uses_live_envelope(self):
        settings = Settings(api_id=1, api_hash="hash")

        with patch("telegram_mcp.client.TelegramClient", CursorTelegramClient):
            wrapper = TelegramWrapper(settings)

        result = _run(
            wrapper.read_recent_dialog(
                chat="@targetdaddy",
                limit=2,
                include_voice_transcription=True,
            )
        )

        self.assertEqual(result.message_count, 2)
        self.assertEqual(result.data_source, "live_telegram")
        self.assertEqual(len(wrapper.client.transcribe_calls), 2)
        self.assertEqual(result.voice_transcription_status, "complete")

    def test_read_recent_dialog_reports_omitted_voice_transcriptions(self):
        settings = Settings(api_id=1, api_hash="hash")

        with patch("telegram_mcp.client.TelegramClient", CursorTelegramClient):
            wrapper = TelegramWrapper(settings)

        result = _run(
            wrapper.read_recent_dialog(
                chat="@targetdaddy",
                limit=3,
                include_voice_transcription=True,
                max_voice_transcriptions=1,
            )
        )

        self.assertEqual(result.message_count, 3)
        self.assertEqual(len(wrapper.client.transcribe_calls), 1)
        self.assertEqual(result.voice_transcription_status, "partial")
        self.assertEqual(result.voice_transcription_count, 1)
        self.assertEqual(result.omitted_voice_count, 2)
        self.assertEqual(
            [message.voice_transcription_status for message in result.messages],
            ["complete", "omitted", "omitted"],
        )

    def test_read_recent_dialog_reports_pending_voice_transcriptions(self):
        settings = Settings(api_id=1, api_hash="hash")

        with patch("telegram_mcp.client.TelegramClient", PendingVoiceTelegramClient):
            wrapper = TelegramWrapper(settings)

        result = _run(
            wrapper.read_recent_dialog(
                chat="@targetdaddy",
                limit=1,
                include_voice_transcription=True,
            )
        )

        self.assertEqual(result.voice_transcription_status, "partial")
        self.assertEqual(result.messages[0].voice_transcription_status, "pending")
        self.assertIsNone(result.messages[0].voice_transcription)

    def test_read_recent_dialog_reports_failed_voice_transcriptions(self):
        settings = Settings(api_id=1, api_hash="hash")

        with patch("telegram_mcp.client.TelegramClient", FailingTranscriptionTelegramClient):
            wrapper = TelegramWrapper(settings)

        result = _run(
            wrapper.read_recent_dialog(
                chat="@targetdaddy",
                limit=1,
                include_voice_transcription=True,
            )
        )

        self.assertEqual(result.voice_transcription_status, "partial")
        self.assertEqual(result.messages[0].voice_transcription_status, "failed")
        self.assertEqual(
            result.messages[0].voice_transcription_error,
            "TranscribeAudioRequest failed",
        )

    def test_read_recent_dialog_keeps_message_when_transcription_lane_times_out(self):
        settings = Settings(api_id=1, api_hash="hash")

        with patch("telegram_mcp.client.TelegramClient", TimeoutTranscriptionTelegramClient):
            wrapper = TelegramWrapper(settings)

        result = _run(
            wrapper.read_recent_dialog(
                chat="@targetdaddy",
                limit=1,
                include_voice_transcription=True,
            )
        )

        self.assertEqual(result.message_count, 1)
        self.assertEqual(result.voice_transcription_status, "partial")
        self.assertEqual(
            result.messages[0].voice_transcription_status,
            "operation_timeout",
        )

    def test_read_dialog_slice_uses_request_local_sender_cache(self):
        settings = Settings(api_id=1, api_hash="hash")

        with patch("telegram_mcp.client.TelegramClient", SenderCacheTelegramClient):
            wrapper = TelegramWrapper(settings)

        result = _run(wrapper.read_dialog_slice(chat="@targetdaddy", limit=3))

        self.assertEqual(result.sender_resolution_count, 2)
        self.assertEqual(
            [message.get_sender_calls for message in wrapper.client._messages],
            [1, 0, 1],
        )
        scheduler = wrapper._scheduler.snapshot()
        self.assertEqual(
            scheduler["read"]["labels"]["read_dialog_slice"]["succeeded"],
            1,
        )
        self.assertEqual(
            scheduler["enrich"]["labels"]["resolve_message_sender"]["succeeded"],
            2,
        )

    def test_read_dialog_slice_can_skip_sender_resolution_for_fast_mode(self):
        settings = Settings(api_id=1, api_hash="hash")

        with patch("telegram_mcp.client.TelegramClient", SenderCacheTelegramClient):
            wrapper = TelegramWrapper(settings)

        result = _run(
            wrapper.read_dialog_slice(
                chat="@targetdaddy",
                limit=3,
                include_sender_name=False,
            )
        )

        self.assertEqual(result.sender_resolution_count, 0)
        self.assertEqual([message.sender_name for message in result.messages], ["", "", ""])
        self.assertEqual(
            [message.get_sender_calls for message in wrapper.client._messages],
            [0, 0, 0],
        )

    def test_read_dialog_slice_applies_hard_message_cap(self):
        settings = Settings(api_id=1, api_hash="hash", read_max_messages=2)

        with patch("telegram_mcp.client.TelegramClient", OutputCapTelegramClient):
            wrapper = TelegramWrapper(settings)

        result = _run(
            wrapper.read_dialog_slice(
                chat="@targetdaddy",
                limit=10,
                include_sender_name=False,
            )
        )

        self.assertEqual([message.id for message in result.messages], [1, 2])
        self.assertTrue(result.truncated)
        self.assertEqual(result.truncated_reason, "message_limit")
        self.assertTrue(result.has_more_before)
        self.assertEqual(result.next_offset_id, 2)
        self.assertEqual(wrapper.client.iter_messages_kwargs[0]["limit"], 3)

    def test_read_dialog_slice_applies_hard_character_cap(self):
        settings = Settings(
            api_id=1,
            api_hash="hash",
            read_max_chars=5,
            read_max_messages=10,
        )

        with patch("telegram_mcp.client.TelegramClient", OutputCapTelegramClient):
            wrapper = TelegramWrapper(settings)
            wrapper.client._messages = [
                OutputCapMessage(message_id=1, text="abcdef"),
                OutputCapMessage(message_id=2, text="tail"),
            ]

        result = _run(
            wrapper.read_dialog_slice(
                chat="@targetdaddy",
                limit=2,
                include_sender_name=False,
            )
        )

        self.assertEqual(len(result.messages), 1)
        self.assertEqual(result.messages[0].text, "ab...")
        self.assertTrue(result.truncated)
        self.assertEqual(result.truncated_reason, "char_limit")
        self.assertTrue(result.has_more_before)

    def test_read_dialog_slice_applies_hard_media_cap(self):
        settings = Settings(
            api_id=1,
            api_hash="hash",
            read_max_media_items=1,
            read_max_messages=10,
        )

        with patch("telegram_mcp.client.TelegramClient", OutputCapTelegramClient):
            wrapper = TelegramWrapper(settings)

        result = _run(
            wrapper.read_dialog_slice(
                chat="@targetdaddy",
                limit=3,
                include_sender_name=False,
            )
        )

        self.assertEqual([message.id for message in result.messages], [1])
        self.assertTrue(result.truncated)
        self.assertEqual(result.truncated_reason, "media_limit")

    def test_read_recent_dialog_reuses_non_user_dialog_ref_without_numeric_fallback(self):
        settings = Settings(api_id=1, api_hash="hash")

        with patch("telegram_mcp.client.TelegramClient", NonUserDialogTelegramClient):
            with patch(
                "telegram_mcp.client_chats.get_entity_type",
                lambda entity: getattr(entity, "_forced_type", "unknown"),
            ):
                with patch(
                    "telegram_mcp.client_chats.get_display_name",
                    lambda entity: getattr(entity, "_forced_name", str(entity.id)),
                ):
                    wrapper = TelegramWrapper(settings)
                    handle = _run(wrapper.resolve_dialog("@channelslug"))
                    result = _run(wrapper.read_recent_dialog(chat=handle.dialog_ref, limit=1))

        self.assertEqual(handle.dialog_ref, "tg://dialog/channel/777")
        self.assertEqual(result.chat.dialog_ref, handle.dialog_ref)
        self.assertEqual(wrapper.client.get_entity_calls, ["@channelslug"])

    def test_search_dialog_messages_scopes_to_one_dialog(self):
        settings = Settings(api_id=1, api_hash="hash")

        with patch("telegram_mcp.client.TelegramClient", DummyTelegramClient):
            wrapper = TelegramWrapper(settings)

        result = _run(
            wrapper.search_dialog_messages(
                chat="@targetdaddy",
                query="hello",
                limit=5,
            )
        )

        self.assertEqual(result.chat.username, "targetdaddy")
        self.assertEqual(result.message_count, 1)

    def test_search_dialog_messages_reuses_short_dialog_cache(self):
        settings = Settings(api_id=1, api_hash="hash")

        with patch("telegram_mcp.client.TelegramClient", DummyTelegramClient):
            wrapper = TelegramWrapper(settings)

        first = _run(
            wrapper.search_dialog_messages(
                chat="@TargetDaddy",
                query="hello",
                limit=5,
                include_sender_name=False,
            )
        )
        second = _run(
            wrapper.search_dialog_messages(
                chat="@targetdaddy",
                query="hello",
                limit=5,
                include_sender_name=False,
            )
        )

        self.assertIs(first, second)
        self.assertEqual(wrapper.client.get_entity_calls, ["@TargetDaddy"])

    def test_search_dialog_messages_reports_hard_cap_truncation(self):
        settings = Settings(api_id=1, api_hash="hash", read_max_messages=1)

        with patch("telegram_mcp.client.TelegramClient", OutputCapTelegramClient):
            wrapper = TelegramWrapper(settings)

        result = _run(
            wrapper.search_dialog_messages(
                chat="@targetdaddy",
                query="hello",
                limit=10,
                include_sender_name=False,
            )
        )

        self.assertEqual([message.id for message in result.messages], [1])
        self.assertEqual(result.message_count, 1)
        self.assertTrue(result.truncated)
        self.assertEqual(result.truncated_reason, "message_limit")
        self.assertTrue(result.has_more_before)

    def test_read_dialog_by_date_rejects_invalid_date_range_with_typed_error(self):
        settings = Settings(api_id=1, api_hash="hash")

        with patch("telegram_mcp.client.TelegramClient", DateRangeTelegramClient):
            wrapper = TelegramWrapper(settings)

        with self.assertRaises(ToolContractError) as ctx:
            _run(
                wrapper.read_dialog_by_date(
                    chat="@targetdaddy",
                    date_from="2026-04-17",
                    date_to="2026-04-16",
                )
            )

        self.assertEqual(ctx.exception.code, "invalid_date_range")

    def test_read_recent_dialog_rejects_unknown_dialog_ref_with_typed_error(self):
        settings = Settings(api_id=1, api_hash="hash")

        with patch("telegram_mcp.client.TelegramClient", DummyTelegramClient):
            wrapper = TelegramWrapper(settings)

        with self.assertRaises(ToolContractError) as ctx:
            _run(wrapper.read_recent_dialog(chat="tg://dialog/channel/777", limit=1))

        self.assertEqual(ctx.exception.code, "dialog_not_found")

    def test_send_dialog_message_uses_existing_send_path(self):
        settings = Settings(api_id=1, api_hash="hash", write_approval_required=False)

        with patch("telegram_mcp.client.TelegramClient", DummyTelegramClient):
            wrapper = TelegramWrapper(settings)

        preview = _run(wrapper.prepare_send_message(chat="@targetdaddy", text="hello"))

        result = _run(wrapper.send_dialog_message(**preview.send_args_preview))

        self.assertEqual(result.text, "hello")
        self.assertEqual(wrapper.client.send_message_calls[0]["parse_mode"], "md")

    def test_reply_in_dialog_uses_existing_reply_path(self):
        settings = Settings(api_id=1, api_hash="hash", write_approval_required=False)

        with patch("telegram_mcp.client.TelegramClient", DummyTelegramClient):
            wrapper = TelegramWrapper(settings)

        preview = _run(wrapper.prepare_reply_message(chat="@targetdaddy", message_id=77, text="pong"))

        result = _run(wrapper.reply_in_dialog(**preview.send_args_preview))

        self.assertEqual(result.reply_to_msg_id, 77)
        self.assertEqual(wrapper.client.send_message_calls[0]["reply_to"], 77)

    def test_send_dialog_message_allows_direct_send_when_approval_disabled(self):
        settings = Settings(api_id=1, api_hash="hash", write_approval_required=False)

        with patch("telegram_mcp.client.TelegramClient", DummyTelegramClient):
            wrapper = TelegramWrapper(settings)

        result = _run(wrapper.send_dialog_message(chat="@targetdaddy", text="hello"))

        self.assertEqual(result.text, "hello")
        self.assertEqual(wrapper.client.send_message_calls[0]["entity"].username, "targetdaddy")

    def test_send_dialog_message_rejects_changed_preview_payload(self):
        settings = Settings(api_id=1, api_hash="hash", write_approval_required=False)

        with patch("telegram_mcp.client.TelegramClient", DummyTelegramClient):
            wrapper = TelegramWrapper(settings)

        preview = _run(wrapper.prepare_send_message(chat="@targetdaddy", text="hello"))
        args = dict(preview.send_args_preview)
        args["text"] = "changed"

        with self.assertRaises(ToolContractError) as ctx:
            _run(wrapper.send_dialog_message(**args))

        self.assertEqual(ctx.exception.code, "confirmation_payload_mismatch")
        self.assertEqual(wrapper.client.send_message_calls, [])

    def test_send_confirmation_token_is_single_use(self):
        settings = Settings(api_id=1, api_hash="hash", write_approval_required=False)

        with patch("telegram_mcp.client.TelegramClient", DummyTelegramClient):
            wrapper = TelegramWrapper(settings)

        preview = _run(wrapper.prepare_send_message(chat="@targetdaddy", text="hello"))
        _run(wrapper.send_dialog_message(**preview.send_args_preview))

        with self.assertRaises(ToolContractError) as ctx:
            _run(wrapper.send_dialog_message(**preview.send_args_preview))

        self.assertEqual(ctx.exception.code, "invalid_confirmation_token")

    def test_read_dialog_slice_returns_chat_info_and_messages(self):
        settings = Settings(api_id=1, api_hash="hash")

        with patch("telegram_mcp.client.TelegramClient", DummyTelegramClient):
            wrapper = TelegramWrapper(settings)

        result = _run(wrapper.read_dialog_slice(chat="@targetdaddy"))

        self.assertEqual(result.chat.id, 1)
        self.assertEqual(result.chat.name, "1")
        self.assertEqual(result.chat.type, "unknown")
        self.assertEqual(len(result.messages), 1)
        self.assertEqual(wrapper.client.get_entity_calls, ["@targetdaddy"])
        self.assertEqual(len(wrapper.client.get_input_entity_calls), 1)

    def test_list_messages_rejects_negative_offset_id(self):
        settings = Settings(api_id=1, api_hash="hash")

        with patch("telegram_mcp.client.TelegramClient", DummyTelegramClient):
            wrapper = TelegramWrapper(settings)

        with self.assertRaises(ToolContractError) as ctx:
            _run(wrapper.list_messages(chat=1, offset_id=-1))

        self.assertEqual(ctx.exception.code, "invalid_pagination")
        self.assertEqual(wrapper.client.get_entity_calls, [])

    def test_read_dialog_slice_rejects_inverted_min_max_ids(self):
        settings = Settings(api_id=1, api_hash="hash")

        with patch("telegram_mcp.client.TelegramClient", DummyTelegramClient):
            wrapper = TelegramWrapper(settings)

        with self.assertRaises(ToolContractError) as ctx:
            _run(wrapper.read_dialog_slice(chat=1, min_id=10, max_id=5))

        self.assertEqual(ctx.exception.code, "invalid_pagination")

    def test_read_dialog_slice_applies_date_bounds(self):
        settings = Settings(api_id=1, api_hash="hash")

        with patch("telegram_mcp.client.TelegramClient", DateRangeTelegramClient):
            wrapper = TelegramWrapper(settings)

        result = _run(
            wrapper.read_dialog_slice(
                chat=1,
                date_from="2026-04-16",
                date_to="2026-04-16",
            )
        )

        self.assertEqual([message.id for message in result.messages], [102])
        self.assertEqual(
            wrapper.client.iter_messages_kwargs[0]["offset_date"],
            datetime(2026, 4, 17, 0, 0, tzinfo=timezone.utc),
        )

    def test_read_dialog_slice_returns_cursor_for_next_page(self):
        settings = Settings(api_id=1, api_hash="hash")

        with patch("telegram_mcp.client.TelegramClient", CursorTelegramClient):
            wrapper = TelegramWrapper(settings)

        first_page = _run(
            wrapper.read_dialog_slice(
                chat=1,
                limit=2,
                date_from="2026-04-16",
                date_to="2026-04-16",
            )
        )

        self.assertEqual([message.id for message in first_page.messages], [301, 302])
        self.assertTrue(first_page.has_more_before)
        self.assertEqual(first_page.next_offset_id, 302)
        self.assertEqual(wrapper.client.iter_messages_kwargs[0]["limit"], 3)

    def test_resolve_username_and_list_messages_share_canonical_entity_cache(self):
        settings = Settings(api_id=1, api_hash="hash")

        with patch("telegram_mcp.client.TelegramClient", DummyTelegramClient):
            wrapper = TelegramWrapper(settings)

        chat = _run(wrapper.resolve_username("targetdaddy"))
        messages = _run(wrapper.list_messages(chat=chat.id))

        self.assertEqual(chat.id, 1)
        self.assertEqual(len(messages), 1)
        self.assertEqual(wrapper.client.get_entity_calls, ["@targetdaddy"])

    def test_list_messages_reuses_cached_input_peer(self):
        settings = Settings(api_id=1, api_hash="hash")

        with patch("telegram_mcp.client.TelegramClient", DummyTelegramClient):
            wrapper = TelegramWrapper(settings)

        _run(wrapper.list_messages(chat=1))
        _run(wrapper.list_messages(chat="1"))

        self.assertEqual(wrapper.client.get_entity_calls, [1])
        self.assertEqual(len(wrapper.client.get_input_entity_calls), 1)

    def test_list_messages_skips_transcription_by_default(self):
        settings = Settings(api_id=1, api_hash="hash")

        with patch("telegram_mcp.client.TelegramClient", DummyTelegramClient):
            wrapper = TelegramWrapper(settings)

        messages = _run(wrapper.list_messages(chat=1))

        self.assertEqual(len(messages), 1)
        self.assertIsNone(messages[0].voice_transcription)
        self.assertEqual(wrapper.client.transcribe_calls, [])

    def test_list_messages_transcribes_document_backed_voice_messages(self):
        settings = Settings(api_id=1, api_hash="hash")

        with patch("telegram_mcp.client.TelegramClient", DocumentVoiceTelegramClient):
            wrapper = TelegramWrapper(settings)

        messages = _run(
            wrapper.list_messages(chat=1, include_voice_transcription=True)
        )

        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].media_type, "voice")
        self.assertEqual(messages[0].voice_transcription, "text")
        self.assertEqual(messages[0].voice_transcription_status, "complete")
        self.assertEqual(len(wrapper.client.transcribe_calls), 1)

    def test_list_messages_includes_media_duration_seconds(self):
        settings = Settings(api_id=1, api_hash="hash")

        with patch("telegram_mcp.client.TelegramClient", DurationTelegramClient):
            wrapper = TelegramWrapper(settings)

        messages = _run(wrapper.list_messages(chat=1))

        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].duration_seconds, 37)

    def test_health_check_includes_runtime_endpoint_for_http_mode(self):
        settings = Settings(api_id=1, api_hash="hash")

        with patch("telegram_mcp.client.TelegramClient", DummyTelegramClient):
            wrapper = TelegramWrapper(settings)

        with patch(
            "telegram_mcp.runtime.get_runtime_report",
            return_value={
                "transport": "streamable-http",
                "shared_client": True,
                "host": "127.0.0.1",
                "port": 8799,
                "http_path": "/mcp",
                "endpoint_url": "http://127.0.0.1:8799/mcp",
            },
        ):
            health = _run(wrapper.health_check())

        self.assertEqual(health.transport, "streamable-http")
        self.assertEqual(health.endpoint_url, "http://127.0.0.1:8799/mcp")

    def test_doctor_check_uses_settings_transport_when_env_is_missing(self):
        settings = Settings(api_id=1, api_hash="hash", mcp_transport="sse")

        with patch("telegram_mcp.client.TelegramClient", DummyTelegramClient):
            wrapper = TelegramWrapper(settings)

        with patch.dict("os.environ", {}, clear=True):
            doctor = _run(wrapper.doctor_check())

        self.assertEqual(doctor.transport, "sse")
        self.assertEqual(doctor.checks["transport"], "sse")
        self.assertEqual(doctor.checks["download_cleanup"], "enabled")
        self.assertIsNotNone(doctor.download_cleanup)
        self.assertIsNotNone(doctor.runtime_stats)
        self.assertIn("dialog_read_cache_hit", doctor.runtime_stats)
        self.assertIn("dialog_read_cache_hit_rate", doctor.runtime_stats)
        self.assertIsNotNone(doctor.runtime_compat)
        self.assertTrue(doctor.runtime_compat["ok"])

    def test_archive_chat_invalidates_list_chats_cache(self):
        settings = Settings(api_id=1, api_hash="hash")

        with patch("telegram_mcp.client.TelegramClient", DummyTelegramClient):
            wrapper = TelegramWrapper(settings)

        with patch.object(wrapper, "invalidate_cache") as invalidate_cache:
            _run(wrapper.archive_chat(chat=1))

        invalidate_cache.assert_called_once_with("list_chats")

    def test_unarchive_chat_invalidates_list_chats_cache(self):
        settings = Settings(api_id=1, api_hash="hash")

        with patch("telegram_mcp.client.TelegramClient", DummyTelegramClient):
            wrapper = TelegramWrapper(settings)

        with patch.object(wrapper, "invalidate_cache") as invalidate_cache:
            _run(wrapper.unarchive_chat(chat=1))

        invalidate_cache.assert_called_once_with("list_chats")

    def test_mute_and_unmute_chat_stay_available_from_privacy_mixin(self):
        settings = Settings(api_id=1, api_hash="hash")

        with patch("telegram_mcp.client.TelegramClient", DummyTelegramClient):
            wrapper = TelegramWrapper(settings)

        _run(wrapper.mute_chat(chat=1))
        _run(wrapper.unmute_chat(chat=1))

        self.assertEqual(
            [type(request).__name__ for request in wrapper.client.transcribe_calls],
            ["UpdateNotifySettingsRequest", "UpdateNotifySettingsRequest"],
        )

    def test_list_contacts_uses_cache_from_contact_mixin(self):
        settings = Settings(api_id=1, api_hash="hash")

        with patch("telegram_mcp.client.TelegramClient", ContactTelegramClient):
            wrapper = TelegramWrapper(settings)

        first = _run(wrapper.list_contacts())
        second = _run(wrapper.list_contacts())

        self.assertEqual(first, second)
        self.assertEqual(first[0].username, "ada")
        self.assertEqual(
            [type(request).__name__ for request in wrapper.client.requests],
            ["GetContactsRequest"],
        )

    def test_add_contact_invalidates_contacts_cache_from_contact_mixin(self):
        settings = Settings(api_id=1, api_hash="hash")

        with patch("telegram_mcp.client.TelegramClient", ContactTelegramClient):
            wrapper = TelegramWrapper(settings)

        with patch.object(wrapper, "invalidate_cache") as invalidate_cache:
            contact = _run(
                wrapper.add_contact(
                    phone="+200",
                    first_name="Grace",
                    last_name="Hopper",
                )
            )

        self.assertEqual(contact.username, "grace")
        invalidate_cache.assert_called_once_with("list_contacts")

    def test_export_story_link_stays_available_from_story_mixin(self):
        settings = Settings(api_id=1, api_hash="hash")

        with patch("telegram_mcp.client.TelegramClient", StoryLinkTelegramClient):
            wrapper = TelegramWrapper(settings)

        result = _run(wrapper.export_story_link(peer=1, story_id=5))

        self.assertEqual(result, "https://t.me/story")
        self.assertEqual(
            [type(request).__name__ for request in wrapper.client.requests],
            ["ExportStoryLinkRequest"],
        )

    def test_update_profile_requires_payload_from_profile_mixin(self):
        settings = Settings(api_id=1, api_hash="hash")

        with patch("telegram_mcp.client.TelegramClient", DummyTelegramClient):
            wrapper = TelegramWrapper(settings)

        with self.assertRaises(ValueError):
            _run(wrapper.update_profile())

    def test_reply_to_message_invalidates_dialog_and_list_caches(self):
        settings = Settings(api_id=1, api_hash="hash")

        with patch("telegram_mcp.client.TelegramClient", DummyTelegramClient):
            wrapper = TelegramWrapper(settings)

        with patch.object(wrapper, "invalidate_cache") as invalidate_cache:
            _run(wrapper.reply_to_message(chat="@targetdaddy", message_id=77, text="pong"))

        self.assertEqual(
            [call.args[0] for call in invalidate_cache.call_args_list],
            ["dialog_read:", "dialog_search:", "list_chats"],
        )

    def test_direct_message_writes_invalidate_dialog_and_list_caches(self):
        settings = Settings(api_id=1, api_hash="hash")

        with patch("telegram_mcp.client.TelegramClient", WriteToolsTelegramClient):
            wrapper = TelegramWrapper(settings)

        operations = (
            lambda: wrapper.send_message(chat="@targetdaddy", text="hello"),
            lambda: wrapper.forward_messages(
                from_chat="@targetdaddy",
                to_chat="@targetdaddy",
                message_ids=[7],
            ),
            lambda: wrapper.create_poll(
                chat="@targetdaddy",
                question="Pick one",
                options=["A", "B"],
            ),
            lambda: wrapper.send_message_with_buttons(
                chat="@targetdaddy",
                text="open",
                buttons=[[{"text": "Open", "url": "https://example.com"}]],
            ),
        )

        for operation in operations:
            with patch.object(wrapper, "invalidate_cache") as invalidate_cache:
                _run(operation())
            self.assertEqual(
                [call.args[0] for call in invalidate_cache.call_args_list],
                ["dialog_read:", "dialog_search:", "list_chats"],
            )

    def test_write_audit_logs_metadata_without_message_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            audit_path = Path(tmp) / "write-audit.jsonl"
            settings = Settings(
                api_id=1,
                api_hash="hash",
                write_audit_log_path=audit_path,
            )

            with patch("telegram_mcp.client.TelegramClient", DummyTelegramClient):
                wrapper = TelegramWrapper(settings)

            _run(wrapper.send_message(chat="@targetdaddy", text="secret payload"))

            raw_audit = audit_path.read_text(encoding="utf-8")
            events = [
                json.loads(line)
                for line in raw_audit.splitlines()
                if line.strip()
            ]

        self.assertEqual([event["status"] for event in events], ["started", "succeeded"])
        self.assertEqual({event["operation"] for event in events}, {"send_message"})
        self.assertNotIn("secret payload", raw_audit)

    def test_media_writes_log_audit_without_caption_or_file_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            audit_path = Path(tmp) / "write-audit.jsonl"
            settings = Settings(
                api_id=1,
                api_hash="hash",
                write_audit_log_path=audit_path,
            )

            with patch("telegram_mcp.client.TelegramClient", DummyTelegramClient):
                wrapper = TelegramWrapper(settings)

            wrapper.client.send_file = AsyncMock(
                return_value=SimpleNamespace(
                    id=901,
                    chat_id=1,
                    sender_id=777,
                    date=datetime(2026, 4, 17, tzinfo=timezone.utc),
                    text="caption",
                    document=None,
                    photo=None,
                    sticker=None,
                    gif=None,
                    voice=False,
                    video=False,
                    audio=False,
                )
            )

            _run(
                wrapper.send_file(
                    chat="@targetdaddy",
                    file_path="/tmp/secret-file.txt",
                    caption="secret caption",
                )
            )
            _run(wrapper.send_voice(chat="@targetdaddy", file_path="/tmp/secret.oga"))

            raw_audit = audit_path.read_text(encoding="utf-8")
            events = [
                json.loads(line)
                for line in raw_audit.splitlines()
                if line.strip()
            ]

        self.assertEqual(
            [(event["operation"], event["status"], event["lane"]) for event in events],
            [
                ("send_file", "started", "media"),
                ("send_file", "succeeded", "media"),
                ("send_voice", "started", "media"),
                ("send_voice", "succeeded", "media"),
            ],
        )
        self.assertNotIn("secret-file", raw_audit)
        self.assertNotIn("secret caption", raw_audit)
        self.assertNotIn("secret.oga", raw_audit)

    def test_failed_write_audit_omits_raw_error_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            audit_path = Path(tmp) / "write-audit.jsonl"
            settings = Settings(
                api_id=1,
                api_hash="hash",
                write_audit_log_path=audit_path,
            )

            with patch("telegram_mcp.client.TelegramClient", DummyTelegramClient):
                wrapper = TelegramWrapper(settings)

            wrapper.client.send_file = AsyncMock(
                side_effect=RuntimeError("secret /tmp/secret-file.txt")
            )

            with self.assertRaises(RuntimeError):
                _run(wrapper.send_file(chat="@targetdaddy", file_path="/tmp/secret-file.txt"))

            raw_audit = audit_path.read_text(encoding="utf-8")
            events = [
                json.loads(line)
                for line in raw_audit.splitlines()
                if line.strip()
            ]

        self.assertEqual([event["status"] for event in events], ["started", "failed"])
        self.assertEqual(events[-1]["error_type"], "RuntimeError")
        self.assertNotIn("secret-file", raw_audit)
        self.assertNotIn("secret /tmp", raw_audit)

    def test_send_file_invalidates_dialog_and_list_caches(self):
        settings = Settings(api_id=1, api_hash="hash")

        with patch("telegram_mcp.client.TelegramClient", DummyTelegramClient):
            wrapper = TelegramWrapper(settings)

        wrapper.client.send_file = AsyncMock(
            return_value=SimpleNamespace(
                id=901,
                chat_id=1,
                sender_id=777,
                date=datetime(2026, 4, 17, tzinfo=timezone.utc),
                text="caption",
                document=None,
                photo=None,
                sticker=None,
                gif=None,
                voice=False,
                video=False,
                audio=False,
            )
        )

        with patch.object(wrapper, "invalidate_cache") as invalidate_cache:
            _run(wrapper.send_file(chat="@targetdaddy", file_path="/tmp/demo.txt"))

        self.assertEqual(
            [call.args[0] for call in invalidate_cache.call_args_list],
            ["dialog_read:", "dialog_search:", "list_chats"],
        )

    def test_edit_delete_and_send_voice_invalidate_dialog_and_list_caches(self):
        settings = Settings(api_id=1, api_hash="hash")

        with patch("telegram_mcp.client.TelegramClient", DummyTelegramClient):
            wrapper = TelegramWrapper(settings)

        wrapper.client.edit_message = AsyncMock(
            return_value=SimpleNamespace(
                id=5,
                chat_id=1,
                sender_id=777,
                date=datetime(2026, 4, 17, tzinfo=timezone.utc),
                text="edited",
                edit_date=None,
            )
        )
        wrapper.client.delete_messages = AsyncMock(return_value=[])
        wrapper.client.send_file = AsyncMock(
            return_value=SimpleNamespace(
                id=6,
                chat_id=1,
                sender_id=777,
                date=datetime(2026, 4, 17, tzinfo=timezone.utc),
                text="",
                edit_date=None,
            )
        )

        for operation in (
            lambda: wrapper.edit_message(
                chat="@targetdaddy",
                message_id=5,
                text="edited",
            ),
            lambda: wrapper.delete_messages(chat="@targetdaddy", message_ids=[5]),
            lambda: wrapper.send_voice(chat="@targetdaddy", file_path="/tmp/demo.oga"),
        ):
            with patch.object(wrapper, "invalidate_cache") as invalidate_cache:
                _run(operation())
            self.assertEqual(
                [call.args[0] for call in invalidate_cache.call_args_list],
                ["dialog_read:", "dialog_search:", "list_chats"],
            )

    def test_pin_unpin_and_reaction_invalidate_dialog_and_list_caches(self):
        settings = Settings(api_id=1, api_hash="hash")

        with patch("telegram_mcp.client.TelegramClient", DummyTelegramClient):
            wrapper = TelegramWrapper(settings)

        wrapper.client.pin_message = AsyncMock(return_value=True)
        wrapper.client.unpin_message = AsyncMock(return_value=True)
        for operation in (
            lambda: wrapper.pin_message(chat="@targetdaddy", message_id=5),
            lambda: wrapper.unpin_message(chat="@targetdaddy", message_id=5),
            lambda: wrapper.send_reaction(
                chat="@targetdaddy",
                message_id=5,
                emoji="👍",
            ),
        ):
            with patch.object(wrapper, "invalidate_cache") as invalidate_cache:
                _run(operation())
            self.assertEqual(
                [call.args[0] for call in invalidate_cache.call_args_list],
                ["dialog_read:", "dialog_search:", "list_chats"],
            )

        self.assertEqual(wrapper._runtime_stats["cache_invalidated_after_write"], 3)

    def test_download_media_skips_retention_cleanup_by_default(self):
        now = 1_800_000_000.0

        with tempfile.TemporaryDirectory() as tmp:
            download_dir = Path(tmp)
            old_file = download_dir / "old.mp4"
            old_file.write_bytes(b"old")
            os.utime(old_file, (now - 8 * 24 * 60 * 60, now - 8 * 24 * 60 * 60))

            recent_file = download_dir / "recent.mp4"
            recent_file.write_bytes(b"recent")
            os.utime(
                recent_file,
                (now - 2 * 24 * 60 * 60, now - 2 * 24 * 60 * 60),
            )

            settings = Settings(
                api_id=1,
                api_hash="hash",
                download_dir=download_dir,
                download_retention_days=0,
                download_cleanup_interval_seconds=0,
            )

            with patch("telegram_mcp.client.TelegramClient", DownloadTelegramClient):
                wrapper = TelegramWrapper(settings)
                with patch("telegram_mcp.client.time.time", return_value=now):
                    result = _run(wrapper.download_media(chat="@targetdaddy", message_id=7))

            self.assertEqual(result.file_name, "new.oga")
            self.assertTrue(old_file.exists())
            self.assertTrue(recent_file.exists())
            self.assertTrue((download_dir / "new.oga").exists())

    def test_download_media_runs_retention_cleanup_when_enabled(self):
        now = 1_800_000_000.0

        with tempfile.TemporaryDirectory() as tmp:
            download_dir = Path(tmp)
            old_file = download_dir / "old.mp4"
            old_file.write_bytes(b"old")
            os.utime(old_file, (now - 8 * 24 * 60 * 60, now - 8 * 24 * 60 * 60))

            settings = Settings(
                api_id=1,
                api_hash="hash",
                download_dir=download_dir,
                download_retention_days=7,
                download_cleanup_interval_seconds=0,
            )

            with patch("telegram_mcp.client.TelegramClient", DownloadTelegramClient):
                wrapper = TelegramWrapper(settings)
                with patch("telegram_mcp.client.time.time", return_value=now):
                    result = _run(wrapper.download_media(chat="@targetdaddy", message_id=7))

            self.assertEqual(result.file_name, "new.oga")
            self.assertFalse(old_file.exists())
            self.assertTrue((download_dir / "new.oga").exists())

    def test_download_media_continues_when_retention_cleanup_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            download_dir = Path(tmp)
            settings = Settings(
                api_id=1,
                api_hash="hash",
                download_dir=download_dir,
                download_retention_days=7,
                download_cleanup_interval_seconds=0,
            )

            with patch("telegram_mcp.client.TelegramClient", DownloadTelegramClient):
                wrapper = TelegramWrapper(settings)
                with patch(
                    "telegram_mcp.client.cleanup_download_dir",
                    side_effect=PermissionError("nope"),
                ):
                    result = _run(wrapper.download_media(chat="@targetdaddy", message_id=7))

            self.assertEqual(result.file_name, "new.oga")
            self.assertTrue((download_dir / "new.oga").exists())

    def test_download_media_batch_dedupes_work_but_preserves_requested_items(self):
        with tempfile.TemporaryDirectory() as tmp:
            download_dir = Path(tmp)
            settings = Settings(
                api_id=1,
                api_hash="hash",
                download_dir=download_dir,
                download_retention_days=7,
                download_cleanup_interval_seconds=0,
            )

            with patch("telegram_mcp.client.TelegramClient", BatchDownloadTelegramClient):
                wrapper = TelegramWrapper(settings)
                with patch(
                    "telegram_mcp.client.cleanup_download_dir",
                    return_value=SimpleNamespace(deleted_files=0, deleted_bytes=0, errors=[]),
                ) as cleanup:
                    result = _run(
                        wrapper.download_media_batch(
                            chat="@targetdaddy",
                            message_ids=[7, 7, 8, 404],
                            concurrency=2,
                        )
                    )

            self.assertEqual(wrapper.client.get_entity_calls, ["@targetdaddy"])
            self.assertEqual(wrapper.client.get_messages_calls, [[7, 8, 404]])
            cleanup.assert_called_once()
            self.assertEqual(wrapper.client.download_media_calls, [7, 8])
            self.assertEqual(wrapper._runtime_stats["download_media_batch_dedupe_count"], 1)
            self.assertEqual(
                wrapper._runtime_stats["download_media_batch_effective_concurrency"],
                2,
            )
            self.assertEqual(result.requested_count, 4)
            self.assertEqual(result.success_count, 2)
            self.assertEqual(result.failed_count, 2)
            self.assertEqual(result.items[0].media.file_name, "7.oga")
            self.assertEqual(result.items[1].message_id, 7)
            self.assertEqual(result.items[1].media.file_name, "7.oga")
            self.assertEqual(result.items[2].error, "RuntimeError: download failed")
            self.assertEqual(result.items[3].error, "message_not_found")
            self.assertTrue((download_dir / "7.oga").exists())

    def test_download_media_batch_clamps_concurrency_to_scheduler_media_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings(
                api_id=1,
                api_hash="hash",
                download_dir=Path(tmp),
                scheduler_media_concurrency=1,
            )

            with patch("telegram_mcp.client.TelegramClient", BatchDownloadTelegramClient):
                wrapper = TelegramWrapper(settings)
                result = _run(
                    wrapper.download_media_batch(
                        chat="@targetdaddy",
                        message_ids=[7, 10, 11],
                        concurrency=3,
                    )
                )

            self.assertEqual(result.success_count, 3)
            self.assertEqual(wrapper.client.download_media_calls, [7, 10, 11])
            self.assertEqual(wrapper.client.max_active_downloads, 1)

    def test_download_media_batch_rejects_too_many_unique_items(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings(
                api_id=1,
                api_hash="hash",
                download_dir=Path(tmp),
                read_max_media_items=2,
            )

            with patch("telegram_mcp.client.TelegramClient", BatchDownloadTelegramClient):
                wrapper = TelegramWrapper(settings)
                with self.assertRaises(ToolContractError) as ctx:
                    _run(
                        wrapper.download_media_batch(
                            chat="@targetdaddy",
                            message_ids=[7, 10, 11],
                            concurrency=1,
                        )
                    )

            self.assertEqual(ctx.exception.code, "media_batch_too_large")
            self.assertEqual(wrapper.client.get_entity_calls, [])
            self.assertEqual(wrapper.client.get_messages_calls, [])

    def test_download_media_batch_rejects_duplicate_amplification(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings(
                api_id=1,
                api_hash="hash",
                download_dir=Path(tmp),
                read_max_media_items=2,
            )

            with patch("telegram_mcp.client.TelegramClient", BatchDownloadTelegramClient):
                wrapper = TelegramWrapper(settings)
                with self.assertRaises(ToolContractError) as ctx:
                    _run(
                        wrapper.download_media_batch(
                            chat="@targetdaddy",
                            message_ids=[7, 7, 7],
                            concurrency=1,
                        )
                    )

            self.assertEqual(ctx.exception.code, "media_batch_too_large")
            self.assertEqual(wrapper.client.get_entity_calls, [])

    def test_prepare_media_inspection_manifest_does_not_download(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            known_media = root / "known.oga"
            known_media.write_bytes(b"known")
            settings = Settings(
                api_id=1,
                api_hash="hash",
                download_dir=root / "downloads",
                download_registry_path=root / "downloads.sqlite3",
            )

            with patch("telegram_mcp.client.TelegramClient", ManifestTelegramClient):
                wrapper = TelegramWrapper(settings)
                wrapper._record_downloaded_message_media(
                    chat_id=1,
                    chat_ref="@targetdaddy",
                    message_id=7,
                    path=str(known_media),
                    remote_media_ref="document:1007:dc4:size17",
                )
                result = _run(
                    wrapper.prepare_media_inspection_manifest(
                        chat="@targetdaddy",
                        limit=10,
                    )
                )

            self.assertEqual(result.media_count, 1)
            self.assertEqual(result.items[0].message_id, 7)
            self.assertEqual(result.items[0].media_type, "audio")
            self.assertEqual(result.items[0].mime_type, "audio/ogg")
            self.assertEqual(result.items[0].file_size, 17)
            self.assertEqual(result.items[0].remote_media_ref, "document:1007:dc4:size17")
            self.assertEqual(result.items[0].local_path, str(known_media))
            self.assertEqual(wrapper.client.get_messages_calls, [[7]])

    def test_prepare_media_inspection_manifest_ignores_stale_local_media_ref(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            stale_media = root / "stale.oga"
            stale_media.write_bytes(b"stale")
            settings = Settings(
                api_id=1,
                api_hash="hash",
                download_dir=root / "downloads",
                download_registry_path=root / "downloads.sqlite3",
            )

            with patch("telegram_mcp.client.TelegramClient", ManifestTelegramClient):
                wrapper = TelegramWrapper(settings)
                wrapper._record_downloaded_message_media(
                    chat_id=1,
                    chat_ref="@targetdaddy",
                    message_id=7,
                    path=str(stale_media),
                    remote_media_ref="document:old:dc4:size5",
                )
                result = _run(
                    wrapper.prepare_media_inspection_manifest(
                        chat="@targetdaddy",
                        limit=10,
                    )
                )

            self.assertEqual(result.items[0].remote_media_ref, "document:1007:dc4:size17")
            self.assertIsNone(result.items[0].local_path)

    def test_prepare_send_and_reply_message_are_preview_only(self):
        settings = Settings(api_id=1, api_hash="hash")

        with patch("telegram_mcp.client.TelegramClient", DummyTelegramClient):
            wrapper = TelegramWrapper(settings)

        wrapper.client.send_message = AsyncMock(side_effect=AssertionError("sent"))

        send_preview = _run(
            wrapper.prepare_send_message(
                chat="@targetdaddy",
                text="hello",
            )
        )
        reply_preview = _run(
            wrapper.prepare_reply_message(
                chat="@targetdaddy",
                message_id=7,
                text="reply",
            )
        )

        self.assertTrue(send_preview.preview_only)
        self.assertEqual(send_preview.send_tool, "telegram_confirmed_send")
        self.assertEqual(send_preview.send_args_preview["text"], "hello")
        self.assertTrue(send_preview.confirmation_token)
        self.assertEqual(send_preview.send_args_preview["confirmation_token"], send_preview.confirmation_token)
        self.assertTrue(reply_preview.preview_only)
        self.assertEqual(reply_preview.send_tool, "telegram_confirmed_send")
        self.assertEqual(reply_preview.reply_target_message_id, 7)
        self.assertTrue(reply_preview.confirmation_token)
        wrapper.client.send_message.assert_not_awaited()

    def test_mark_as_read_invalidates_list_chats_cache(self):
        settings = Settings(api_id=1, api_hash="hash")

        with patch("telegram_mcp.client.TelegramClient", DummyTelegramClient):
            wrapper = TelegramWrapper(settings)

        wrapper.client.send_read_acknowledge = AsyncMock(return_value=True)

        with patch.object(wrapper, "invalidate_cache") as invalidate_cache:
            _run(wrapper.mark_as_read(chat=1))

        invalidate_cache.assert_called_once_with("list_chats")

    def test_list_messages_emits_latency_diagnostics_when_enabled(self):
        settings = Settings(
            api_id=1,
            api_hash="hash",
            mcp_include_diagnostics=True,
        )

        with patch("telegram_mcp.client.TelegramClient", DummyTelegramClient):
            with patch("telegram_mcp.client.log") as log:
                wrapper = TelegramWrapper(settings)
                result = _run(wrapper.list_messages(chat=1))

        self.assertEqual(len(result), 1)
        self.assertTrue(
            any(
                call.args
                and call.args[0] == "telegram_read_completed"
                and call.kwargs.get("operation") == "list_messages"
                for call in log.info.call_args_list
            )
        )

    def test_list_messages_skips_latency_diagnostics_when_disabled(self):
        settings = Settings(
            api_id=1,
            api_hash="hash",
            mcp_include_diagnostics=False,
        )

        with patch("telegram_mcp.client.TelegramClient", DummyTelegramClient):
            with patch("telegram_mcp.client.log") as log:
                wrapper = TelegramWrapper(settings)
                result = _run(wrapper.list_messages(chat=1))

        self.assertEqual(len(result), 1)
        self.assertFalse(
            any(
                call.args
                and call.args[0] == "telegram_read_completed"
                for call in log.info.call_args_list
            )
        )


def _run(awaitable):
    import asyncio

    return asyncio.run(awaitable)
