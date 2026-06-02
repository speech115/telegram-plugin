# Telegram App Facade Design

- Date: `2026-04-17`
- Status: `implemented`
- Repo: `/Users/sereja/Projects/families/telegram/telegram-digest/telegram-mcp`

## Summary

`telegram-mcp` already has a rich low-level Telegram surface: chats, messages, media,
search, replies, reactions, group management, contacts, stories, and profile tools.
The missing piece is not capability. The missing piece is a stable high-level front
door for common agent tasks and a future app-style connector surface built on top of
that front door.

This design keeps the rich API, adds a task-oriented dialog facade inside the same
server, updates Codex routing to prefer that facade for normal Telegram work, and
then exposes the same facade through an app-style connector UX.

## Problem

Today Telegram work is split across too many mental routes:

- raw `telegram-mcp` tools,
- local `telegram-mirror` helpers,
- live-fallback logic for fresh personal dialogs,
- low-level tool composition such as `resolve_username -> read_dialog_slice`.

This causes three concrete problems:

1. The agent has to choose a route instead of just doing the task.
2. Common requests like "read today's chat with X" are built from low-level pieces.
3. There is no clean product-grade front door equivalent to `Gmail`.

## Goals

- Preserve the full rich Telegram MCP API.
- Add a high-level, task-oriented dialog facade for common agent workflows.
- Make normal live Telegram work prefer the new facade by default.
- Keep `telegram-mirror` as an archival and analytics layer, not the main live front door.
- Prepare a connector/app surface that can feel like `Gmail` without duplicating backend logic.

## Non-goals

- Replace the existing low-level `telegram-mcp` tools.
- Build a second Telegram backend in `telegram-mirror`.
- Route archival and heavy historical analytics through the live app facade.
- Promise that literal `app://telegram` wiring is solved purely inside this repo. Some
  connector plumbing may live at the platform layer.

## User-facing target

The first product-grade Telegram experience should make these requests work through a
single obvious route:

- "прочитай переписку с `@targetdaddy` за сегодня"
- "покажи последние 30 сообщений с `X`"
- "найди у него сообщение про `Y`"
- "ответь ему `Z`"

## Design principles

1. One Telegram backend, not two.
2. Rich API stays rich.
3. High-level facade is orchestration-only and composes existing primitives.
4. App-style connector should sit on top of the facade, not bypass it.
5. Mirror is a sidecar for archives and analysis, not the default live UX.
6. Facade reads must go through one canonical internal read engine.
7. Live facade must fail honestly instead of silently falling back to mirror data.

## Layered architecture

### Layer 1: Rich MCP API

The existing `telegram-mcp` tool surface remains intact and can keep expanding.

Examples already present in the repo:

- `list_chats`
- `resolve_username`
- `list_messages`
- `read_dialog_slice`
- `search_messages`
- `send_message`
- `reply_to_message`
- `edit_message`
- `delete_messages`
- `forward_messages`
- `download_media`
- `transcribe_voice`
- reactions, pinned messages, stories, contacts, groups, profile tools

This is the power-user and low-level automation layer.

### Layer 2: High-level dialog facade

Add a new tool set inside the same `telegram-mcp` server for normal agent tasks.

Recommended first facade tools:

- `resolve_dialog`
- `read_dialog_by_date`
- `read_recent_dialog`
- `search_dialog_messages`
- `send_dialog_message`
- `reply_in_dialog`

This layer must be implemented as orchestration over the existing client methods and
tools. It should not create a second Telethon path or duplicate message fetching logic.

### Layer 3: App / connector front door

Expose the facade as the default user-facing Telegram surface, similar in spirit to
`Gmail`.

The app layer should stay intentionally smaller than the rich MCP API. It exists to
make common flows obvious and stable, not to surface every Telegram operation.

## High-level MCP contract

### `resolve_dialog(query: str) -> DialogHandle`

Resolve a human query such as `@username`, display name, phone, or numeric id into a
canonical dialog handle.

Suggested response shape:

- `dialog_ref`
- `id`
- `name`
- `type`
- `username`
- `resolved_from`
- `match_confidence`

Behavior:

- Prefer deterministic exact matches.
- Return a typed `ambiguous_dialog` error when multiple candidates remain.
- Return a typed `dialog_not_found` error when nothing resolves.
- `dialog_ref` must be stable and reusable across subsequent facade calls in the same
  session so callers do not have to re-resolve the same dialog repeatedly.

### Facade input rule

All high-level facade tools should accept either:

- a raw human query such as `@username`, display name, phone, or numeric id, or
- a previously returned canonical `dialog_ref`

This keeps agent UX simple while still allowing efficient multi-step flows after one
resolution pass.

### `read_dialog_by_date(chat, date_from, date_to, page_size?, total_limit?) -> DialogReadResult`

Primary read tool for "today", "yesterday", or explicit date windows.

Suggested response shape:

- `chat`
- `messages`
- `message_count`
- `has_more_before`
- `next_offset_id`
- `range`
- `data_source`

Behavior:

- Use live Telegram data.
- Reuse existing `read_dialog_slice` logic internally.
- Keep response shape stable across future paging.
- Do not silently fall back to mirror data. If live transport is unavailable, return a
  typed live-transport error.

### `read_recent_dialog(chat, limit=50) -> DialogReadResult`

Sugar for recent context reads without explicit dates.

### `search_dialog_messages(chat, query, limit=20) -> DialogReadResult`

Scoped search within one dialog, not global Telegram search by default.

### `send_dialog_message(chat, text, parse_mode?) -> MessageInfo`

Send a message through the same canonical dialog resolution path.

### `reply_in_dialog(chat, message_id, text, parse_mode?) -> MessageInfo`

Reply to a specific message through the same canonical dialog resolution path.

## App contract

The app-facing surface should expose a smaller, stable action set:

- find dialog
- read dialog
- search in dialog
- send message
- reply to message

The app contract should use the high-level facade and not depend on callers knowing
about low-level Telegram tool composition.

## Routing policy

Default routing after this design lands:

- fresh personal-dialog tasks -> high-level live Telegram facade
- ordinary send/reply/search tasks -> high-level live Telegram facade
- power-user Telegram automation -> raw rich `telegram-mcp` tools
- archival or heavy historical analysis -> `telegram-mirror`

This removes mirror-first thinking from normal conversational Telegram work.

Facade rule:

- no silent mirror fallback inside facade reads
- mirror stays an explicit sidecar chosen by routing or by caller intent

## Error model

Prefer typed, human-meaningful errors over raw Telegram or Telethon exceptions.

Target error categories:

- `dialog_not_found`
- `ambiguous_dialog`
- `message_not_found`
- `permission_denied`
- `invalid_date_range`
- `transport_unavailable`

Raw backend exception details may be included as debug metadata, but not as the main
contract.

## Data shape rules

To keep agent UX clean:

1. `chat` must always be canonicalized.
2. `read` results should share one stable envelope shape.
3. `data_source` must always be explicit.
4. Paging metadata must be included in high-level reads.
5. The facade should prefer typed payloads over ad-hoc JSON blobs.
6. All facade read tools should be implemented on top of one shared internal read
   pipeline so ordering, paging, error mapping, and data shaping cannot drift.

## Internal read engine

Externally the facade may expose several user-friendly read tools, but internally they
should all funnel into one canonical read engine.

Expected facade wrappers:

- `read_dialog_by_date`
- `read_recent_dialog`
- `search_dialog_messages`

Expected shared internal responsibilities:

- canonical dialog resolution
- paging state handling
- message ordering
- stable response envelope shaping
- typed error mapping
- explicit `data_source`

This avoids three almost-identical read paths diverging over time.

## Implementation strategy

### Shipping slice 1

Implement the facade inside `telegram-mcp`:

- add typed models for dialog-handle and read-result envelopes if needed
- add a new tool module, for example `dialog_facade_tools.py`
- wire new tools into `tools/__init__.py` and `server.py`
- back the facade with existing client primitives instead of new Telegram fetch code

### Shipping slice 2

Update Codex routing to use the new facade as the default live Telegram front door for
normal tasks.

### Shipping slice 3

Run the new facade through real live usage before freezing an app-facing contract.

Acceptance for this slice:

- common read/send/reply tasks work through the facade without mirror routing hacks
- the error surface is understandable in normal use
- no hidden pressure appears to add mirror fallback into the facade itself

### Shipping slice 4

Expose the same facade through an app-style connector surface. If platform-level
connector wiring is needed, this repo should still remain the backend source of truth.

## Testing strategy

Add focused tests in `telegram-mcp` for:

- exact dialog resolution
- ambiguous dialog resolution
- date-window reads
- recent reads
- scoped dialog search
- send/reply happy paths
- error mapping for not-found and invalid input cases

Do not rely on mirror-based tests for this layer.

## Risks

### Risk: duplicate logic across facade and raw tools

Mitigation:

- facade only orchestrates existing client methods
- avoid reimplementing message collection, date filtering, and entity resolution

### Risk: app connector promise outruns platform wiring reality

Mitigation:

- ship the facade first
- treat connector wiring as a thin layer after backend contract is stable

### Risk: mirror remains on the critical path by habit

Mitigation:

- explicitly route normal live tasks to the new facade
- keep mirror documentation focused on archive and analytics use cases

### Risk: app contract hardens too early

Mitigation:

- do not freeze the app-facing contract before the facade survives real live usage
- let routing and operator feedback shake out weak spots first

## Recommendation

Ship the layered design in this order:

1. rich MCP stays as-is
2. high-level dialog facade lands in `telegram-mcp`
3. Codex routing switches to the facade for common live Telegram tasks
4. the facade is exercised in real usage and adjusted if needed
5. app / connector UX is added on top

This gives a Telegram experience that feels like `Gmail` without sacrificing the full
capability surface already present in the repo.
