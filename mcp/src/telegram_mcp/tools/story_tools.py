"""Story retrieval tools."""

from __future__ import annotations

from mcp.types import ToolAnnotations

from .. import runtime
from ..errors import tool_error_handler
from ..types import (
    LinkResult,
    StoriesResult,
    StoryInfo,
    StoryViewersResult,
    StoryViewInfo,
    StoryViewsResult,
    StoryViewsStats,
)

READONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True)


async def get_peer_stories(peer: str | int) -> StoriesResult:
    """Get active (non-expired) stories of a user or channel."""
    tg = await runtime.get_tg()
    stories = await tg.get_peer_stories(peer)
    return StoriesResult(stories=stories)


async def get_stories_by_id(peer: str | int, story_ids: list[int]) -> StoriesResult:
    """Get specific stories by their IDs."""
    tg = await runtime.get_tg()
    stories = await tg.get_stories_by_id(peer, story_ids)
    return StoriesResult(stories=stories)


async def get_pinned_stories(
    peer: str | int, limit: int = 20, offset_id: int = 0
) -> StoriesResult:
    """Get pinned stories of a user or channel."""
    tg = await runtime.get_tg()
    stories = await tg.get_pinned_stories(peer, limit=limit, offset_id=offset_id)
    return StoriesResult(stories=stories)


async def get_stories_archive(
    peer: str | int, limit: int = 20, offset_id: int = 0
) -> StoriesResult:
    """Get archived stories (your own stories history)."""
    tg = await runtime.get_tg()
    stories = await tg.get_stories_archive(peer, limit=limit, offset_id=offset_id)
    return StoriesResult(stories=stories)


async def get_story_views(peer: str | int, story_ids: list[int]) -> StoryViewsResult:
    """Get view statistics for stories."""
    tg = await runtime.get_tg()
    stats = await tg.get_story_views(peer, story_ids)
    return StoryViewsResult(stats=stats)


async def get_story_viewers(
    peer: str | int, story_id: int, limit: int = 50, offset: str = ""
) -> StoryViewersResult:
    """Get list of users who viewed a story."""
    tg = await runtime.get_tg()
    viewers = await tg.get_story_viewers(peer, story_id, limit=limit, offset=offset)
    return StoryViewersResult(viewers=viewers)


async def export_story_link(peer: str | int, story_id: int) -> LinkResult:
    """Get a t.me link to a specific story."""
    tg = await runtime.get_tg()
    link = await tg.export_story_link(peer, story_id)
    return LinkResult(link=link)


def register(mcp) -> None:
    mcp.tool(annotations=READONLY)(tool_error_handler(get_peer_stories))
    mcp.tool(annotations=READONLY)(tool_error_handler(get_stories_by_id))
    mcp.tool(annotations=READONLY)(tool_error_handler(get_pinned_stories))
    mcp.tool(annotations=READONLY)(tool_error_handler(get_stories_archive))
    mcp.tool(annotations=READONLY)(tool_error_handler(get_story_views))
    mcp.tool(annotations=READONLY)(tool_error_handler(get_story_viewers))
    mcp.tool(annotations=READONLY)(tool_error_handler(export_story_link))
