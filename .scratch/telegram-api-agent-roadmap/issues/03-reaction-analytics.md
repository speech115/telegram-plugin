# Reaction Analytics

Status: done

## Goal

Add read-only reaction analytics beyond `send_reaction`.

## Acceptance Criteria

- Get reactions for specific messages.
- List reaction users where Telegram exposes them.
- Get unread reactions.
- Mark reactions as read only after explicit review because it mutates read state.

## Implemented

- `get_message_reactions`
- `get_unread_reactions`
- `read_reactions` intentionally not added to the read-only analytics surface.

## Safety

Separate read-only analytics from read-state mutation.
