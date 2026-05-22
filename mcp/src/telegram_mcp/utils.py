"""Entity resolution and error formatting."""

from __future__ import annotations

import re

from telethon import TelegramClient
from telethon.tl.functions.messages import CheckChatInviteRequest
from telethon.tl.types import (
    Channel,
    Chat,
    User,
)

INVITE_LINK_RE = re.compile(
    r"^(?:https?://)?t\.me/(?:joinchat/|\+)(?P<token>[A-Za-z0-9_-]+)$",
    re.IGNORECASE,
)
USERNAME_LINK_RE = re.compile(
    r"^(?:https?://)?t\.me/(?P<username>[A-Za-z0-9_]{3,})/?$",
    re.IGNORECASE,
)


async def resolve_entity(client: TelegramClient, chat: str | int):
    """Resolve a chat identifier to a Telethon entity.

    Accepts: numeric ID (int or str), @username, phone number, "me", or a t.me link.
    """
    # Handle int directly (from MCP transport JSON coercion)
    if isinstance(chat, int):
        return await client.get_entity(chat)

    normalized = str(chat).strip()
    invite_match = INVITE_LINK_RE.match(normalized)
    if invite_match:
        invite = await client(CheckChatInviteRequest(invite_match.group("token")))
        invite_chat = getattr(invite, "chat", None)
        if invite_chat is None:
            raise ValueError(
                "Invite link is valid, but the current Telegram account is not a member of that chat."
            )
        return invite_chat

    username_match = USERNAME_LINK_RE.match(normalized)
    if username_match:
        normalized = f"@{username_match.group('username')}"

    if normalized == "me":
        return await client.get_me()

    # Try numeric ID
    try:
        entity_id = int(normalized)
        return await client.get_entity(entity_id)
    except (ValueError, TypeError):
        pass

    # @username or phone
    return await client.get_entity(normalized)


def get_entity_type(entity) -> str:
    if isinstance(entity, User):
        return "bot" if entity.bot else "user"
    if isinstance(entity, Channel):
        return "channel" if entity.broadcast else "supergroup"
    if isinstance(entity, Chat):
        return "group"
    return "unknown"


def get_display_name(entity) -> str:
    if isinstance(entity, User):
        name = entity.first_name or ""
        if entity.last_name:
            name += f" {entity.last_name}"
        return name
    if isinstance(entity, (Chat, Channel)):
        return entity.title or ""
    return str(entity.id) if hasattr(entity, "id") else "Unknown"


def get_sender_name(sender) -> str:
    if sender is None:
        return ""
    if isinstance(sender, User):
        name = sender.first_name or ""
        if sender.last_name:
            name += f" {sender.last_name}"
        return name
    if isinstance(sender, (Chat, Channel)):
        return sender.title or ""
    return ""


def format_error(e: Exception) -> str:
    """Format an exception for MCP tool response."""
    return f"Error: {type(e).__name__}: {e}"


def get_media_type(message) -> str | None:
    """Detect media type from a Telethon message."""
    if getattr(message, "photo", None):
        return "photo"
    document = getattr(message, "document", None)
    if document:
        attrs = {type(a).__name__ for a in (document.attributes or [])}
        if "DocumentAttributeVideo" in attrs:
            return "video"
        if "DocumentAttributeAudio" in attrs:
            if any(
                getattr(a, "voice", False)
                for a in document.attributes
            ):
                return "voice"
            return "audio"
        if "DocumentAttributeSticker" in attrs:
            return "sticker"
        if "DocumentAttributeAnimated" in attrs:
            return "gif"
        if getattr(message, "voice", None):
            return "voice"
        if getattr(message, "video", None):
            return "video"
        if getattr(message, "audio", None):
            return "audio"
        return "document"
    if getattr(message, "sticker", None):
        return "sticker"
    if getattr(message, "gif", None):
        return "gif"
    if getattr(message, "voice", None):
        return "voice"
    if getattr(message, "video", None):
        return "video"
    if getattr(message, "audio", None):
        return "audio"
    return None


def _coerce_duration_seconds(value) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value) if value >= 0 else None
    return None


def get_media_duration_seconds(message) -> int | None:
    """Extract media duration from Telethon message metadata without downloading the file."""
    file = getattr(message, "file", None)
    duration = _coerce_duration_seconds(getattr(file, "duration", None))
    if duration is not None:
        return duration

    document = getattr(message, "document", None)
    if document:
        for attr in getattr(document, "attributes", []) or []:
            duration = _coerce_duration_seconds(getattr(attr, "duration", None))
            if duration is not None:
                return duration

    for attr_name in ("audio", "voice", "video", "video_note"):
        media = getattr(message, attr_name, None)
        duration = _coerce_duration_seconds(getattr(media, "duration", None))
        if duration is not None:
            return duration

    return None
