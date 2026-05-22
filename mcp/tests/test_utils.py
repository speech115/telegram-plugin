import asyncio
import sys
import types
import unittest
from types import SimpleNamespace


telethon = types.ModuleType("telethon")
telethon.TelegramClient = object

telethon_tl = types.ModuleType("telethon.tl")
telethon_tl_functions = types.ModuleType("telethon.tl.functions")
telethon_tl_functions_messages = types.ModuleType("telethon.tl.functions.messages")
telethon_tl_types = types.ModuleType("telethon.tl.types")


class CheckChatInviteRequest:
    def __init__(self, hash: str) -> None:
        self.hash = hash


class Channel:
    pass


class Chat:
    pass


class User:
    pass


telethon_tl_functions_messages.CheckChatInviteRequest = CheckChatInviteRequest
telethon_tl_types.Channel = Channel
telethon_tl_types.Chat = Chat
telethon_tl_types.User = User

sys.modules.setdefault("telethon", telethon)
sys.modules.setdefault("telethon.tl", telethon_tl)
sys.modules.setdefault("telethon.tl.functions", telethon_tl_functions)
sys.modules.setdefault("telethon.tl.functions.messages", telethon_tl_functions_messages)
sys.modules.setdefault("telethon.tl.types", telethon_tl_types)

from telegram_mcp.utils import resolve_entity


class _InviteReadyClient:
    def __init__(self) -> None:
        self.entity_calls: list[object] = []
        self.request_calls: list[object] = []

    async def get_entity(self, chat):
        self.entity_calls.append(chat)
        return SimpleNamespace(id=1, title="channel")

    async def __call__(self, request):
        self.request_calls.append(request)
        return SimpleNamespace(chat=SimpleNamespace(id=-1001, title="notes-channel"))


class ResolveEntityTests(unittest.TestCase):
    def test_resolve_entity_accepts_invite_link_for_joined_chat(self) -> None:
        client = _InviteReadyClient()

        entity = asyncio.run(resolve_entity(client, "https://t.me/+nJg6_FByDWdkZDBi"))

        self.assertEqual(entity.id, -1001)
        self.assertEqual(client.entity_calls, [])
        self.assertEqual(len(client.request_calls), 1)
        self.assertEqual(client.request_calls[0].hash, "nJg6_FByDWdkZDBi")
