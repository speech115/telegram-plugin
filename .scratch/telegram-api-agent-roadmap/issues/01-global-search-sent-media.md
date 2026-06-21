# Global Search And Sent Media

Status: done

## Goal

Add read-only MCP tools for global message search and sent-media search.

## Acceptance Criteria

- `global_search` searches across dialogs and returns `MessagesResult`.
- `sent_media_search` returns recent outgoing media messages with normal `MessageInfo` shape.
- `sent_media_search` is bounded by `max_dialogs` because raw MTProto sent-media search is not reliable across all user-account filters.
- Both tools are read-only and registered in full MCP surface.
- Tests cover registration and wrapper method calls.

## Notes

Prefer Telethon MTProto requests already available in the current dependency. Do not add Pyrogram.

## Implemented

- `global_search`
- `sent_media_search`
