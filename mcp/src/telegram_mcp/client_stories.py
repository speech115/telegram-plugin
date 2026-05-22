"""Story operations for TelegramWrapper."""

from __future__ import annotations

from telethon.tl.functions.stories import (
    ExportStoryLinkRequest,
    GetPeerStoriesRequest,
    GetPinnedStoriesRequest,
    GetStoriesArchiveRequest,
    GetStoriesByIDRequest,
    GetStoriesViewsRequest,
    GetStoryViewsListRequest,
)
from telethon.tl.types import (
    MessageMediaDocument,
    MessageMediaPhoto,
    ReactionEmoji,
    StoryItem,
)

from .types import StoryInfo, StoryViewInfo, StoryViewsStats
from .utils import get_display_name


class StoryOperationsMixin:
    """Story read and analytics operations."""

    def _story_item_to_info(self, item: StoryItem, peer_id: int) -> StoryInfo:
        media_type = None
        has_media = item.media is not None
        if has_media:
            if isinstance(item.media, MessageMediaPhoto):
                media_type = "photo"
            elif isinstance(item.media, MessageMediaDocument):
                media_type = "video"

        views_stats = None
        if item.views is not None:
            views_stats = StoryViewsStats(
                views_count=item.views.views_count,
                forwards_count=item.views.forwards_count or 0,
                reactions_count=item.views.reactions_count or 0,
                recent_viewers=list(item.views.recent_viewers or []),
            )

        return StoryInfo(
            id=item.id,
            peer_id=peer_id,
            date=item.date,
            expire_date=item.expire_date,
            caption=item.caption or "",
            has_media=has_media,
            media_type=media_type,
            views=views_stats,
            pinned=item.pinned or False,
            public=item.public or False,
            is_outgoing=item.out or False,
            close_friends=item.close_friends or False,
        )

    async def get_peer_stories(self, peer: str | int) -> list[StoryInfo]:
        entity = await self._resolve_entity(peer)
        input_peer = await self.client.get_input_entity(entity)
        result = await self._run_read(
            "get_peer_stories",
            lambda: self.client(GetPeerStoriesRequest(peer=input_peer)),
        )
        stories = []
        if result.stories and result.stories.stories:
            for item in result.stories.stories:
                if isinstance(item, StoryItem):
                    stories.append(self._story_item_to_info(item, entity.id))
        return stories

    async def get_stories_by_id(
        self, peer: str | int, ids: list[int]
    ) -> list[StoryInfo]:
        entity = await self._resolve_entity(peer)
        input_peer = await self.client.get_input_entity(entity)
        result = await self._run_read(
            "get_stories_by_id",
            lambda: self.client(GetStoriesByIDRequest(peer=input_peer, id=ids)),
        )
        stories = []
        for item in result.stories:
            if isinstance(item, StoryItem):
                stories.append(self._story_item_to_info(item, entity.id))
        return stories

    async def get_pinned_stories(
        self, peer: str | int, limit: int = 20, offset_id: int = 0
    ) -> list[StoryInfo]:
        self._validate_non_negative("limit", limit)
        self._validate_non_negative("offset_id", offset_id)
        entity = await self._resolve_entity(peer)
        input_peer = await self.client.get_input_entity(entity)
        result = await self._run_read(
            "get_pinned_stories",
            lambda: self.client(
                GetPinnedStoriesRequest(
                    peer=input_peer,
                    offset_id=offset_id,
                    limit=limit,
                )
            ),
        )
        stories = []
        for item in result.stories:
            if isinstance(item, StoryItem):
                stories.append(self._story_item_to_info(item, entity.id))
        return stories

    async def get_stories_archive(
        self, peer: str | int, limit: int = 20, offset_id: int = 0
    ) -> list[StoryInfo]:
        self._validate_non_negative("limit", limit)
        self._validate_non_negative("offset_id", offset_id)
        entity = await self._resolve_entity(peer)
        input_peer = await self.client.get_input_entity(entity)
        result = await self._run_read(
            "get_stories_archive",
            lambda: self.client(
                GetStoriesArchiveRequest(
                    peer=input_peer,
                    offset_id=offset_id,
                    limit=limit,
                )
            ),
        )
        stories = []
        for item in result.stories:
            if isinstance(item, StoryItem):
                stories.append(self._story_item_to_info(item, entity.id))
        return stories

    async def get_story_views(
        self, peer: str | int, ids: list[int]
    ) -> list[StoryViewsStats]:
        entity = await self._resolve_entity(peer)
        input_peer = await self.client.get_input_entity(entity)
        result = await self._run_read(
            "get_story_views",
            lambda: self.client(GetStoriesViewsRequest(peer=input_peer, id=ids)),
        )
        stats = []
        for story_view in result.views:
            stats.append(
                StoryViewsStats(
                    views_count=story_view.views_count,
                    forwards_count=story_view.forwards_count or 0,
                    reactions_count=story_view.reactions_count or 0,
                    recent_viewers=list(story_view.recent_viewers or []),
                )
            )
        return stats

    async def get_story_viewers(
        self,
        peer: str | int,
        story_id: int,
        limit: int = 50,
        offset: str = "",
    ) -> list[StoryViewInfo]:
        self._validate_non_negative("limit", limit)
        entity = await self._resolve_entity(peer)
        input_peer = await self.client.get_input_entity(entity)
        result = await self._run_read(
            "get_story_viewers",
            lambda: self.client(
                GetStoryViewsListRequest(
                    peer=input_peer,
                    id=story_id,
                    limit=limit,
                    offset=offset,
                )
            ),
        )
        users_map = {user.id: user for user in result.users}
        viewers = []
        for view in result.views:
            user = users_map.get(view.user_id)
            user_name = get_display_name(user) if user else ""
            reaction = None
            if view.reaction:
                if isinstance(view.reaction, ReactionEmoji):
                    reaction = view.reaction.emoticon
                elif hasattr(view.reaction, "emoticon"):
                    reaction = view.reaction.emoticon
            viewers.append(
                StoryViewInfo(
                    user_id=view.user_id,
                    user_name=user_name,
                    date=view.date,
                    reaction=reaction,
                )
            )
        return viewers

    async def export_story_link(self, peer: str | int, story_id: int) -> str:
        entity = await self._resolve_entity(peer)
        input_peer = await self.client.get_input_entity(entity)
        result = await self._run_read(
            "export_story_link",
            lambda: self.client(ExportStoryLinkRequest(peer=input_peer, id=story_id)),
        )
        return result.link
