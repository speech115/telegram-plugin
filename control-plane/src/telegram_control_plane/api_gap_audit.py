"""Audit official Telegram capability gaps without enabling new writes."""

from __future__ import annotations

from collections import Counter
from typing import Any


CAPABILITIES: tuple[dict[str, Any], ...] = (
    {
        "id": "global_search",
        "title": "Global message search",
        "source": "Telegram user account API",
        "classification": "supported_runtime",
        "evidence": "telegram-mcp exposes global_search",
        "runtime_tools": ["global_search"],
        "next_action": "keep_in_contract_smoke",
    },
    {
        "id": "thread_context",
        "title": "Forum and discussion thread context",
        "source": "Telegram user account API",
        "classification": "supported_runtime",
        "evidence": "telegram-mcp exposes list_forum_topics and get_thread_replies",
        "runtime_tools": [
            "list_forum_topics",
            "get_forum_topics_by_id",
            "get_discussion_message",
            "get_thread_replies",
        ],
        "next_action": "keep_in_contract_smoke",
    },
    {
        "id": "reaction_analytics",
        "title": "Read-only reaction analytics",
        "source": "Telegram user account API",
        "classification": "supported_runtime",
        "evidence": "telegram-mcp exposes get_message_reactions and get_unread_reactions",
        "runtime_tools": ["get_message_reactions", "get_unread_reactions"],
        "next_action": "keep_in_contract_smoke",
    },
    {
        "id": "story_analytics",
        "title": "Story views, viewers, links, and archive reads",
        "source": "Telegram user account API",
        "classification": "supported_runtime",
        "evidence": "telegram-mcp has story read and analytics methods",
        "runtime_tools": [
            "get_peer_stories",
            "get_stories_by_id",
            "get_pinned_stories",
            "get_stories_archive",
            "get_story_views",
            "get_story_viewers",
            "export_story_link",
        ],
        "next_action": "keep_tail_priority_unless_live_story_use_increases",
    },
    {
        "id": "bot_api_rich_messages",
        "title": "Bot API rich messages",
        "source": "Bot API changelog 2026-06-11",
        "classification": "audit_only",
        "evidence": "Needs docs and permission review before any runtime exposure",
        "runtime_tools": [],
        "next_action": "track_changelog_only",
    },
    {
        "id": "bot_api_guest_mode",
        "title": "Bot API guest mode",
        "source": "Bot API changelog 2026-06-11",
        "classification": "audit_only",
        "evidence": "Bot-account capability; not part of owner user-account runtime",
        "runtime_tools": [],
        "next_action": "track_changelog_only",
    },
    {
        "id": "managed_bot_tokens",
        "title": "Managed bot tokens",
        "source": "Bot API changelog 2026-06-11",
        "classification": "blocked_by_permission_model",
        "evidence": "Token management is external-account mutation and needs a separate permission model",
        "runtime_tools": [],
        "next_action": "requires_explicit_bot_token_policy",
    },
    {
        "id": "business_paid_media",
        "title": "Paid media on behalf of business accounts",
        "source": "Bot API changelog 2026-06-11",
        "classification": "blocked_by_permission_model",
        "evidence": "Paid/business writes are out of scope until explicit business-write policy exists",
        "runtime_tools": [],
        "next_action": "requires_explicit_business_write_policy",
    },
    {
        "id": "stars_gifts_paid_media",
        "title": "Stars, gifts, and paid media writes",
        "source": "Telegram monetization surfaces",
        "classification": "blocked_by_permission_model",
        "evidence": "Roadmap explicitly keeps paid/gift writes out of this phase",
        "runtime_tools": [],
        "next_action": "requires_explicit_monetization_policy",
    },
)


def audit_api_gaps() -> dict[str, Any]:
    counts = Counter(str(item["classification"]) for item in CAPABILITIES)
    return {
        "status": "ok",
        "command": "api-gap-audit",
        "capabilities": list(CAPABILITIES),
        "summary": dict(sorted(counts.items())),
        "policy": {
            "default": "audit_only_until_permission_model",
            "blocked_classifications": ["blocked_by_permission_model"],
        },
    }
