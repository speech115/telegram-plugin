from datetime import datetime, timezone

from telegram_mcp.client_message_reads import MessageReadMixin
from telegram_mcp.types import DialogHandle, MessageInfo


class _LatestWrapper(MessageReadMixin):
    def __init__(self, messages):
        self.client = type("Client", (), {"get_messages": lambda _self, _entity, **_kwargs: messages})()
        self.seen_labels = []

    async def _resolve_dialog_with_entity(self, chat):
        return (
            DialogHandle(
                dialog_ref="tg://dialog/channel/1",
                id=1,
                name="Channel",
                type="channel",
                username="channel",
                resolved_from=str(chat),
            ),
            object(),
        )

    async def _run_read(self, label, func):
        self.seen_labels.append(label)
        return func()

    def _emit_read_timing(self, *args, **kwargs):
        return None

    def _message_to_info(self, msg, *, default_chat_id, **kwargs):
        assert default_chat_id == 1
        return MessageInfo(
            id=msg.id,
            chat_id=default_chat_id,
            date=msg.date,
        )


def test_latest_dialog_message_uses_default_chat_id_for_formatter():
    import asyncio

    message = type("Message", (), {"id": 42, "date": datetime.now(timezone.utc)})()
    wrapper = _LatestWrapper([message])

    result = asyncio.run(wrapper.latest_dialog_message("@channel"))

    assert result.message.id == 42
    assert wrapper.seen_labels == ["latest_dialog_message"]


class _ListWrapper(MessageReadMixin):
    def __init__(self, messages):
        self.messages = messages
        self.calls = []
        self.seen_labels = []
        self.client = type("Client", (), {"get_messages": self._get_messages})()

    def _get_messages(self, _entity, **kwargs):
        self.calls.append(kwargs)
        return self.messages

    async def _resolve_dialog_with_entity(self, chat):
        return (
            DialogHandle(
                dialog_ref="tg://dialog/channel/1",
                id=1,
                name="Channel",
                type="channel",
                username="channel",
                resolved_from=str(chat),
            ),
            object(),
        )

    async def _run_read(self, label, func):
        self.seen_labels.append(label)
        return func()

    def _emit_read_timing(self, *args, **kwargs):
        return None

    def _bounded_read_limit(self, limit):
        return min(limit, 20), False

    def _message_to_info(self, msg, *, default_chat_id, **kwargs):
        assert default_chat_id == 1
        return MessageInfo(
            id=msg.id,
            chat_id=default_chat_id,
            date=msg.date,
        )


def test_list_dialog_metadata_uses_filter_and_has_more_marker():
    import asyncio

    now = datetime.now(timezone.utc)
    messages = [
        type("Message", (), {"id": 50, "date": now})(),
        type("Message", (), {"id": 49, "date": now})(),
        type("Message", (), {"id": 48, "date": now})(),
    ]
    wrapper = _ListWrapper(messages)

    result = asyncio.run(wrapper.list_dialog_metadata("@channel", "links", limit=2, offset_id=99))

    assert result.list_type == "links"
    assert result.filter == "InputMessagesFilterUrl"
    assert [message.id for message in result.messages] == [50, 49]
    assert result.has_more_before is True
    assert result.next_offset_id == 49
    assert wrapper.calls[0]["limit"] == 3
    assert wrapper.calls[0]["offset_id"] == 99
    assert type(wrapper.calls[0]["filter"]).__name__ == "InputMessagesFilterUrl"
