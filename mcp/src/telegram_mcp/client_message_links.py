"""Message link helpers for TelegramWrapper."""

from __future__ import annotations

class MessageLinkMixin:
    """Read-only message permalink helpers."""

    async def get_message_link(
        self, chat: str | int, message_id: int
    ) -> str:
        entity = await self._resolve_entity(chat)
        username = getattr(entity, "username", None)

        if username:
            return f"https://t.me/{username}/{message_id}"

        # For private chats/groups/channels without public usernames, use c/ format.
        return f"https://t.me/c/{entity.id}/{message_id}"
