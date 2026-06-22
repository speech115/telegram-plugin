"""Thread, discussion, and forum topic read operations."""

from __future__ import annotations

import time
from typing import Any

from telethon.tl.functions.messages import (
    GetDiscussionMessageRequest,
    GetForumTopicsByIDRequest,
    GetForumTopicsRequest,
)

from .client_message_common import _FetchedMessageRecord, _MessageCollectionStats
from .types import ForumTopicInfo, ForumTopicsResult, ThreadMessagesResult
from .utils import get_media_type


class ThreadOperationsMixin:
    """Read-only helpers for Telegram replies, discussions, and forum topics."""

    def _topic_to_info(self, topic: Any) -> ForumTopicInfo:
        return ForumTopicInfo(
            id=getattr(topic, "id", 0),
            title=getattr(topic, "title", "") or "",
            top_message=getattr(topic, "top_message", None),
            date=getattr(topic, "date", None),
            unread_count=getattr(topic, "unread_count", 0) or 0,
            unread_mentions_count=getattr(topic, "unread_mentions_count", 0) or 0,
            unread_reactions_count=getattr(topic, "unread_reactions_count", 0) or 0,
            closed=bool(getattr(topic, "closed", False)),
            pinned=bool(getattr(topic, "pinned", False)),
            hidden=bool(getattr(topic, "hidden", False)),
            icon_color=getattr(topic, "icon_color", None),
            icon_emoji_id=getattr(topic, "icon_emoji_id", None),
        )

    async def list_forum_topics(
        self,
        chat: str | int,
        limit: int = 20,
        q: str | None = None,
        offset_id: int = 0,
        offset_topic: int = 0,
    ) -> ForumTopicsResult:
        started_at = time.perf_counter()
        self._validate_non_negative("limit", limit)
        self._validate_non_negative("offset_id", offset_id)
        self._validate_non_negative("offset_topic", offset_topic)
        if limit <= 0:
            return ForumTopicsResult(topics=[], count=0)

        peer = await self._resolve_input_entity(chat)

        async def fetch_topics():
            return await self.client(
                GetForumTopicsRequest(
                    peer=peer,
                    offset_date=None,
                    offset_id=offset_id,
                    offset_topic=offset_topic,
                    limit=limit,
                    q=q or None,
                )
            )

        result = await self._run_read("list_forum_topics", fetch_topics)
        topics = [self._topic_to_info(topic) for topic in getattr(result, "topics", []) or []]
        self._emit_read_timing(
            "list_forum_topics",
            started_at,
            item_count=len(topics),
            query=bool(q),
        )
        return ForumTopicsResult(
            topics=topics,
            count=getattr(result, "count", None),
            order_by_create_date=getattr(result, "order_by_create_date", None),
        )

    async def get_forum_topics_by_id(
        self,
        chat: str | int,
        topic_ids: list[int],
    ) -> ForumTopicsResult:
        started_at = time.perf_counter()
        for topic_id in topic_ids:
            self._validate_non_negative("topic_id", topic_id)
        if not topic_ids:
            return ForumTopicsResult(topics=[], count=0)

        peer = await self._resolve_input_entity(chat)

        async def fetch_topics():
            return await self.client(
                GetForumTopicsByIDRequest(peer=peer, topics=topic_ids)
            )

        result = await self._run_read("get_forum_topics_by_id", fetch_topics)
        topics = [self._topic_to_info(topic) for topic in getattr(result, "topics", []) or []]
        self._emit_read_timing(
            "get_forum_topics_by_id",
            started_at,
            item_count=len(topics),
        )
        return ForumTopicsResult(topics=topics, count=len(topics))

    async def get_discussion_message(
        self,
        chat: str | int,
        message_id: int,
        include_sender_name: bool = True,
    ) -> ThreadMessagesResult:
        started_at = time.perf_counter()
        self._validate_non_negative("message_id", message_id)
        entity = await self._resolve_entity(chat)
        peer = await self._resolve_input_entity(chat)

        async def fetch_discussion():
            result = await self.client(
                GetDiscussionMessageRequest(peer=peer, msg_id=message_id)
            )
            records = [
                _FetchedMessageRecord(message=msg, media_type=get_media_type(msg))
                for msg in getattr(result, "messages", []) or []
            ]
            return records

        records = await self._run_read("get_discussion_message", fetch_discussion)
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
            "get_discussion_message",
            started_at,
            item_count=len(messages),
            sender_resolution_count=stats.sender_resolution_count,
        )
        return ThreadMessagesResult(
            messages=messages,
            message_count=len(messages),
            sender_resolution_count=stats.sender_resolution_count,
        )

    async def get_thread_replies(
        self,
        chat: str | int,
        message_id: int,
        limit: int = 20,
        offset_id: int = 0,
        include_sender_name: bool = True,
    ) -> ThreadMessagesResult:
        started_at = time.perf_counter()
        self._validate_non_negative("message_id", message_id)
        self._validate_non_negative("limit", limit)
        self._validate_non_negative("offset_id", offset_id)
        if limit <= 0:
            return ThreadMessagesResult(messages=[], message_count=0)

        entity = await self._resolve_entity(chat)
        peer = await self._resolve_input_entity(chat)
        fetch_limit, request_was_capped = self._bounded_read_limit(limit)

        async def fetch_replies() -> tuple[list[_FetchedMessageRecord], bool]:
            records = []
            async for msg in self.client.iter_messages(
                entity,
                reply_to=message_id,
                offset_id=offset_id,
                limit=fetch_limit + 1,
            ):
                if len(records) >= fetch_limit:
                    return records, True
                records.append(
                    _FetchedMessageRecord(
                        message=msg,
                        media_type=get_media_type(msg),
                    )
                )
            return records, False

        records, has_more_before = await self._run_read("get_thread_replies", fetch_replies)
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
        initial_reasons = ["message_limit"] if request_was_capped and has_more_before else []
        capped = self._apply_message_caps(
            messages,
            initial_reasons=initial_reasons,
            sender_resolution_count=stats.sender_resolution_count,
        )
        self._emit_read_timing(
            "get_thread_replies",
            started_at,
            item_count=len(capped.messages),
            has_more_before=has_more_before,
            sender_resolution_count=stats.sender_resolution_count,
            truncated=capped.truncated,
            truncated_reason=capped.truncated_reason,
        )
        return ThreadMessagesResult(
            messages=capped.messages,
            message_count=len(capped.messages),
            has_more_before=has_more_before or capped.truncated,
            next_offset_id=capped.messages[-1].id if capped.messages else None,
            sender_resolution_count=stats.sender_resolution_count,
            truncated=capped.truncated,
            truncated_reason=capped.truncated_reason,
        )
