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
