"""Read-only reaction analytics operations."""

from __future__ import annotations

import time
from typing import Any

from telethon.tl.functions.messages import (
    GetMessageReactionsListRequest,
    GetUnreadReactionsRequest,
)
from telethon.tl.types import ReactionCustomEmoji, ReactionEmoji

from .client_message_common import _FetchedMessageRecord, _MessageCollectionStats
from .types import (
    MessageReactionsResult,
    ReactionCountInfo,
    ReactionPeerInfo,
    UnreadReactionsResult,
)
from .utils import get_media_type


class ReactionOperationsMixin:
    """Read-only helpers for message reaction analytics."""

    def _reaction_to_text(self, reaction: Any) -> str:
        if reaction is None:
            return ""
        if isinstance(reaction, ReactionEmoji):
            return reaction.emoticon
        if isinstance(reaction, ReactionCustomEmoji):
            return f"custom:{reaction.document_id}"
        emoticon = getattr(reaction, "emoticon", None)
        if emoticon:
            return str(emoticon)
        document_id = getattr(reaction, "document_id", None)
        if document_id is not None:
            return f"custom:{document_id}"
        return type(reaction).__name__

    def _peer_to_info(self, peer: Any) -> tuple[int | None, str | None]:
        for attr, peer_type in (
            ("user_id", "user"),
            ("chat_id", "chat"),
            ("channel_id", "channel"),
        ):
            value = getattr(peer, attr, None)
            if value is not None:
                return value, peer_type
        return None, type(peer).__name__ if peer is not None else None

    def _reaction_peer_to_info(self, item: Any) -> ReactionPeerInfo:
        peer_id, peer_type = self._peer_to_info(getattr(item, "peer_id", None))
        return ReactionPeerInfo(
            peer_id=peer_id,
            peer_type=peer_type,
            date=getattr(item, "date", None),
            reaction=self._reaction_to_text(getattr(item, "reaction", None)),
            big=bool(getattr(item, "big", False)),
            unread=bool(getattr(item, "unread", False)),
            my=bool(getattr(item, "my", False)),
        )

    async def get_message_reactions(
        self,
        chat: str | int,
        message_id: int,
        limit: int = 50,
        reaction: str | None = None,
        offset: str | None = None,
    ) -> MessageReactionsResult:
        started_at = time.perf_counter()
        self._validate_non_negative("message_id", message_id)
        self._validate_non_negative("limit", limit)
        if limit <= 0:
            return MessageReactionsResult(message_id=message_id)

        entity = await self._resolve_entity(chat)
        peer = await self._resolve_input_entity(chat)
        reaction_filter = ReactionEmoji(emoticon=reaction) if reaction else None

        async def fetch_message():
            return await self.client.get_messages(entity, ids=message_id)

        async def fetch_reactions():
            return await self.client(
                GetMessageReactionsListRequest(
                    peer=peer,
                    id=message_id,
                    limit=limit,
                    reaction=reaction_filter,
                    offset=offset,
                )
            )

        message = await self._run_read("get_message_reactions_message", fetch_message)
        result = await self._run_read("get_message_reactions", fetch_reactions)
        message_reactions = getattr(message, "reactions", None)
        counts = [
            ReactionCountInfo(
                reaction=self._reaction_to_text(getattr(item, "reaction", None)),
                count=getattr(item, "count", 0) or 0,
                chosen_order=getattr(item, "chosen_order", None),
            )
            for item in getattr(message_reactions, "results", []) or []
        ]
        peers = [
            self._reaction_peer_to_info(item)
            for item in getattr(result, "reactions", []) or []
        ]
        next_offset = getattr(result, "next_offset", None)
        self._emit_read_timing(
            "get_message_reactions",
            started_at,
            item_count=len(peers),
            count_count=len(counts),
            filtered=bool(reaction),
        )
        return MessageReactionsResult(
            message_id=message_id,
            counts=counts,
            peers=peers,
            next_offset=next_offset,
            can_see_list=getattr(message_reactions, "can_see_list", None),
            truncated=bool(next_offset),
        )

    async def get_unread_reactions(
        self,
        chat: str | int,
        limit: int = 20,
        offset_id: int = 0,
        min_id: int = 0,
        max_id: int = 0,
        topic_id: int | None = None,
        include_sender_name: bool = True,
    ) -> UnreadReactionsResult:
        started_at = time.perf_counter()
        self._validate_message_window(
            limit=limit,
            offset_id=offset_id,
            min_id=min_id,
            max_id=max_id,
        )
        if topic_id is not None:
            self._validate_non_negative("topic_id", topic_id)
        if limit <= 0:
            return UnreadReactionsResult(messages=[], message_count=0)

        entity = await self._resolve_entity(chat)
        peer = await self._resolve_input_entity(chat)
        fetch_limit, request_was_capped = self._bounded_read_limit(limit)

        async def fetch_unread():
            result = await self.client(
                GetUnreadReactionsRequest(
                    peer=peer,
                    offset_id=offset_id,
                    add_offset=0,
                    limit=fetch_limit + 1,
                    max_id=max_id,
                    min_id=min_id,
                    top_msg_id=topic_id,
                    saved_peer_id=None,
                )
            )
            records = []
            for msg in getattr(result, "messages", []) or []:
                if len(records) >= fetch_limit:
                    return records, True
                records.append(
                    _FetchedMessageRecord(
                        message=msg,
                        media_type=get_media_type(msg),
                    )
                )
            return records, False

        records, has_more_before = await self._run_read("get_unread_reactions", fetch_unread)
        stats = _MessageCollectionStats()
        messages = await self._enrich_message_records(
            entity=entity,
            peer=peer,
            records=records,
            include_voice_transcription=False,
            max_voice_transcriptions=0,
            include_sender_name=include_sender_name,
            stats=stats,
        )
        self._emit_read_timing(
            "get_unread_reactions",
            started_at,
            item_count=len(messages),
            sender_resolution_count=stats.sender_resolution_count,
        )
        return UnreadReactionsResult(
            messages=messages,
            message_count=len(messages),
            next_offset_id=messages[-1].id if messages else None,
            has_more_before=(
                has_more_before
                or (request_was_capped and len(records) >= fetch_limit)
            ),
            sender_resolution_count=stats.sender_resolution_count,
        )
