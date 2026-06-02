"""Chat lookup operations for TelegramWrapper."""

from __future__ import annotations

import time
from typing import Any

from telethon.tl.types import Channel, Chat, User

from .types import ChatInfo, Dialog, DialogHandle, UserInfo
from .utils import get_display_name, get_entity_type


class ChatOperationsMixin:
    """Own-user, dialog, and public chat lookup operations."""

    def _chat_info_from_entity(self, entity: Any) -> ChatInfo:
        return ChatInfo(
            id=entity.id,
            name=get_display_name(entity),
            type=get_entity_type(entity),
            username=getattr(entity, "username", None),
            photo=getattr(entity, "photo", None) is not None,
        )

    # ── User info ──

    async def get_me(self) -> UserInfo:
        cached = self._cache_get("get_me")
        if cached is not None:
            return cached

        me = await self._run_read("get_me", self.client.get_me)
        result = UserInfo(
            id=me.id,
            first_name=me.first_name or "",
            last_name=me.last_name or "",
            username=me.username,
            phone=me.phone,
            is_bot=me.bot or False,
        )
        self._cache_set("get_me", result)
        return result

    # ── Chats ──

    async def list_chats(
        self,
        limit: int = 50,
        chat_type: str | None = None,
        unread_only: bool = False,
        archived: bool = False,
    ) -> list[Dialog]:
        started_at = time.perf_counter()
        self._validate_non_negative("limit", limit)
        cache_key = f"list_chats:{limit}:{chat_type}:{unread_only}:{archived}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            self._emit_read_timing(
                "list_chats",
                started_at,
                cached=True,
                item_count=len(cached),
            )
            return cached

        async def collect_dialogs() -> list[Dialog]:
            dialogs = []
            folder = 1 if archived else 0
            async for d in self.client.iter_dialogs(limit=limit, folder=folder):
                entity = d.entity
                etype = get_entity_type(entity)

                if chat_type and etype != chat_type:
                    continue
                if unread_only and d.unread_count == 0:
                    continue

                dialogs.append(
                    Dialog(
                        id=d.id,
                        name=d.name or "",
                        type=etype,
                        unread_count=d.unread_count,
                        last_message_date=d.date,
                        is_archived=archived,
                        username=getattr(entity, "username", None),
                    )
                )
            return dialogs

        dialogs = await self._run_read("list_chats", collect_dialogs)
        self._cache_set(cache_key, dialogs)
        self._emit_read_timing(
            "list_chats",
            started_at,
            cached=False,
            item_count=len(dialogs),
        )
        return dialogs

    async def get_chat_info(self, chat: str | int) -> ChatInfo:
        cache_key = f"get_chat_info:{chat}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached
        entity = await self._resolve_entity(chat)
        full = await self._run_read(
            "get_chat_info_entity",
            lambda: self.client.get_entity(entity),
        )

        participants_count = None
        description = None

        if isinstance(full, Channel):
            try:
                full_chat = await self._run_read(
                    "get_chat_info_full_channel",
                    lambda: self.client(
                        __import__(
                            "telethon.tl.functions.channels", fromlist=["GetFullChannelRequest"]
                        ).GetFullChannelRequest(full)
                    ),
                )
                participants_count = full_chat.full_chat.participants_count
                description = full_chat.full_chat.about
            except Exception:
                pass
        elif isinstance(full, Chat):
            try:
                full_chat = await self._run_read(
                    "get_chat_info_full_chat",
                    lambda: self.client(
                        __import__(
                            "telethon.tl.functions.messages", fromlist=["GetFullChatRequest"]
                        ).GetFullChatRequest(full.id)
                    ),
                )
                participants_count = full_chat.full_chat.participants_count
                description = full_chat.full_chat.about
            except Exception:
                pass

        result = ChatInfo(
            id=full.id,
            name=get_display_name(full),
            type=get_entity_type(full),
            username=getattr(full, "username", None),
            description=description,
            participants_count=participants_count,
            is_verified=getattr(full, "verified", False) or False,
            is_restricted=getattr(full, "restricted", False) or False,
            photo=full.photo is not None,
        )
        self._cache_set(cache_key, result)
        return result

    async def resolve_username(self, username: str) -> ChatInfo:
        if not username.startswith("@"):
            username = f"@{username}"
        entity = await self._resolve_entity(username)
        return self._chat_info_from_entity(entity)

    async def _resolve_dialog_with_entity(self, query: str | int) -> tuple[DialogHandle, Any]:
        resolved_query = self._coerce_dialog_query(query)
        entity = await self._resolve_entity(resolved_query)
        chat = self._chat_info_from_entity(entity)
        dialog_ref = f"tg://dialog/{chat.type}/{chat.id}"
        self._remember_dialog_ref_entity(dialog_ref, entity)
        return (
            DialogHandle(
                dialog_ref=dialog_ref,
                id=chat.id,
                name=chat.name,
                type=chat.type,
                username=chat.username,
                resolved_from=str(query),
                match_confidence=1.0,
                candidate_count=1,
            ),
            entity,
        )

    async def resolve_dialog(self, query: str | int) -> DialogHandle:
        handle, _ = await self._resolve_dialog_with_entity(query)
        return handle

    # ── Search public ──

    async def search_public_chats(self, query: str) -> list[ChatInfo]:
        from telethon.tl.functions.contacts import SearchRequest as ContactSearchRequest

        result = await self._run_read(
            "search_public_chats",
            lambda: self.client(ContactSearchRequest(q=query, limit=20)),
        )
        chats = []
        for chat in result.chats:
            chats.append(
                ChatInfo(
                    id=chat.id,
                    name=getattr(chat, "title", "") or "",
                    type=get_entity_type(chat),
                    username=getattr(chat, "username", None),
                    photo=chat.photo is not None,
                )
            )
        for user in result.users:
            if isinstance(user, User):
                chats.append(
                    ChatInfo(
                        id=user.id,
                        name=get_display_name(user),
                        type=get_entity_type(user),
                        username=user.username,
                        photo=user.photo is not None,
                    )
                )
        return chats
