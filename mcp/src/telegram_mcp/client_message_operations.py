"""Composed message operations for TelegramWrapper."""

from __future__ import annotations

from .client_message_common import (
    MessageCommonMixin,
    _FetchedMessageRecord,
    _MessageCollectionResult,
    _MessageCollectionStats,
    _TranscriptionOutcome,
)
from .client_message_dialog_reads import MessageDialogReadMixin
from .client_message_facade import MessageFacadeMixin
from .client_message_links import MessageLinkMixin
from .client_message_pinned import MessagePinnedMixin
from .client_message_reads import MessageReadMixin
from .client_message_search import MessageSearchMixin
from .client_message_voice_writes import MessageVoiceWriteMixin
from .client_message_writes import MessageWriteMixin


class MessageOperationsMixin(
    MessageFacadeMixin,
    MessageSearchMixin,
    MessageVoiceWriteMixin,
    MessageWriteMixin,
    MessagePinnedMixin,
    MessageLinkMixin,
    MessageDialogReadMixin,
    MessageReadMixin,
    MessageCommonMixin,
):
    """Message read/write operations composed from focused mixins."""


__all__ = [
    "MessageOperationsMixin",
    "_FetchedMessageRecord",
    "_MessageCollectionResult",
    "_MessageCollectionStats",
    "_TranscriptionOutcome",
]
