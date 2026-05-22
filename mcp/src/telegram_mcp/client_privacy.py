"""Privacy and folder operations for TelegramWrapper."""

from __future__ import annotations

from telethon.tl.functions.account import UpdateNotifySettingsRequest
from telethon.tl.functions.folders import EditPeerFoldersRequest
from telethon.tl.types import (
    InputFolderPeer,
    InputNotifyPeer,
    InputPeerNotifySettings,
)


class PrivacyOperationsMixin:
    """Mute and archive operations."""

    async def mute_chat(self, chat: str | int) -> bool:
        entity = await self._resolve_entity(chat)
        peer = await self.client.get_input_entity(entity)
        await self._run_write(
            "mute_chat",
            lambda: self.client(
                UpdateNotifySettingsRequest(
                    peer=InputNotifyPeer(peer=peer),
                    settings=InputPeerNotifySettings(mute_until=2**31 - 1),
                )
            ),
        )
        return True

    async def unmute_chat(self, chat: str | int) -> bool:
        entity = await self._resolve_entity(chat)
        peer = await self.client.get_input_entity(entity)
        await self._run_write(
            "unmute_chat",
            lambda: self.client(
                UpdateNotifySettingsRequest(
                    peer=InputNotifyPeer(peer=peer),
                    settings=InputPeerNotifySettings(mute_until=0),
                )
            ),
        )
        return True

    async def archive_chat(self, chat: str | int) -> bool:
        entity = await self._resolve_entity(chat)
        peer = await self.client.get_input_entity(entity)
        await self._run_write(
            "archive_chat",
            lambda: self.client(
                EditPeerFoldersRequest(
                    folder_peers=[InputFolderPeer(peer=peer, folder_id=1)]
                )
            ),
        )
        self._invalidate_chat_list_cache()
        return True

    async def unarchive_chat(self, chat: str | int) -> bool:
        entity = await self._resolve_entity(chat)
        peer = await self.client.get_input_entity(entity)
        await self._run_write(
            "unarchive_chat",
            lambda: self.client(
                EditPeerFoldersRequest(
                    folder_peers=[InputFolderPeer(peer=peer, folder_id=0)]
                )
            ),
        )
        self._invalidate_chat_list_cache()
        return True
