# Thread Context And Forum Tools

Status: done

## Goal

Add thread/topic-aware read helpers so agents can keep discussion context.

## Acceptance Criteria

- Read replies for a message.
- Resolve discussion message where Telegram exposes one.
- List forum topics for forum supergroups.
- Return topic/thread identifiers in results where available.

## Implemented

- `list_forum_topics`
- `get_forum_topics_by_id`
- `get_discussion_message`
- `get_thread_replies`

## Safety

Read-only first. Topic management writes are excluded until a separate permission model exists.
