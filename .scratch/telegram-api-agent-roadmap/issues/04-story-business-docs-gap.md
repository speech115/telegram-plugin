# Story Business And Docs Gap Audits

Status: done

## Goal

Make existing story capabilities first-class, add read-only business audits, and track official Telegram API drift.

## Acceptance Criteria

- Story analytics tools are documented as first-class routes.
- Business audit reports connected bots/capabilities without writes.
- Docs gap audit compares official Telegram API docs/changelog concepts against MCP surface.
- Legacy aliases remain available but are not primary docs recommendations.

## Implemented

- `telegram-api-gap-audit`
- Story analytics classified as supported runtime:
  `get_peer_stories`, `get_stories_by_id`, `get_pinned_stories`,
  `get_stories_archive`, `get_story_views`, `get_story_viewers`,
  `export_story_link`
- Bot API rich messages and guest mode are tracked as `audit_only`.
- Managed bot tokens, business paid media, Stars/gifts/paid writes are blocked
  until an explicit permission model exists.
