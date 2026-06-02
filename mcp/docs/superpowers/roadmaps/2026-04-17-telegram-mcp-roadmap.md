# Telegram MCP Roadmap

- Date: `2026-04-17`
- Status: `active`
- Repo: `/Users/sereja/Projects/families/telegram/telegram-digest/telegram-mcp`

## Purpose

This is the repo-level roadmap for `telegram-mcp`, not just the dialog-facade
track. It exists to keep the project direction obvious: what is already solid,
what should happen next, and what can wait.

## Product Thesis

`telegram-mcp` should be the one real live Telegram backend for local agents:

- rich enough for power-user automation,
- simple enough for normal conversational tasks,
- honest about live-vs-archive boundaries,
- boring to operate.

The target shape is:

1. rich raw Telegram MCP API,
2. stable high-level dialog facade for common tasks,
3. task facade v2 for Codex-friendly read/context/draft flows,
4. cleaner routing and eventually an app-style front door built on that facade.

## Done

### Runtime foundation

- shared HTTP daemon path is the default runtime model
- health and doctor flows exist and are scriptable
- local launchd-managed operation is documented and testable

### Rich MCP surface

- repo already exposes the broad Telegram tool layer: chats, messages, media,
  search, replies, reactions, groups, contacts, stories, profile and related
  operations
- this layer stays in place; the roadmap does not replace it

### Live dialog hot-path improvements

- canonical entity/input-peer cache reduces repeated Telethon resolution work
- `read_dialog_slice` collapses dialog meta + message slice into one call
- server-side day filters avoid pulling extra history for single-day reads
- cursor pagination supports page-by-page history traversal

### Facade Shipping Slice 1

- `resolve_dialog`
- `read_dialog_by_date`
- `read_recent_dialog`
- `search_dialog_messages`
- `send_dialog_message`
- `reply_in_dialog`

The facade now has:

- stable same-session `dialog_ref`
- one shared internal read engine
- explicit pagination continuation via `offset_id`
- typed contract errors such as `dialog_not_found`, `invalid_date_range`,
  `permission_denied`, and `transport_unavailable`

### Task facade v2 over the dialog facade

The repo now has a task-shaped layer for the flows Codex actually routes every
day:

- `read_today_dialog`
- `collect_dialog_context`
- `prepare_dialog_reply`

This must stay a thin composition layer over the dialog facade. It is not a
second backend, not an auto-send autopilot, and not a replacement for the rich
Telegram MCP API.

### MCP speed layer

The live facade path now has:

- short dialog read/search cache via `TELEGRAM_DIALOG_READ_CACHE_TTL_SECONDS`
- conservative cache/dedupe key normalization
- dialog read/search invalidation after message-changing writes
- `download_media_batch` dedupe for repeated ids while preserving requested
  result order
- media batch concurrency clamped to the scheduler media lane
- daemon smoke/stress coverage for task facade reads

## Next

### 1. Codex routing over the facade stack

Normal live Telegram tasks should prefer the facade by default instead of
forcing the agent to choose between raw tools, local mirror helpers, and manual
tool composition.

Success looks like:

- read/context/draft tasks route to task facade v2
- explicit send/reply tasks route to dialog facade write tools
- mirror is chosen only for archive or analytics intent
- there is no silent fallback from live facade reads into mirror data

### 2. Facade soak, external contract smoke, and observability

Before app connector packaging, the facade stack should survive real usage and
tighten any rough edges.

Priority checks:

- ambiguity handling for human dialog queries
- stable data shapes across external MCP clients
- stronger external `mcporter` contract smoke for task facade flows
- diagnostics for dialog read/search cache hits and media batch dedupe/clamp
- review whether any remaining error cases still leak raw backend noise

### 3. App connector later

Once the dialog facade, task facade v2, and Codex routing are boring and
trustworthy, add a smaller connector-style surface for the common actions:

- find dialog
- read dialog
- collect context
- prepare reply
- search in dialog
- send message
- reply to message

This should be a thin layer over the facade stack, not a second Telegram backend.

## Later

### Operations and observability

- stronger runtime diagnostics for long-lived daemon health
- clearer runbooks for transport/session failures
- contract checks for external MCP clients, not only in-process tests

### Rich API expansion

Keep expanding the raw Telegram API where it is actually useful:

- advanced moderation/admin helpers
- richer media workflows
- more complete group/channel management
- better bulk and automation-oriented operations

This is allowed, but should not derail the facade/routing path.

### Archive and analytics boundary

Make the line between live Telegram and `telegram-mirror` easier to reason
about:

- live facade for normal conversational work
- mirror for archive, indexing, and historical analysis
- no hidden hybrid behavior

## Explicit Non-Goals

- building a second Telegram backend inside `telegram-mirror`
- building an auto-send autopilot
- removing or shrinking the raw `telegram-mcp` API
- pretending app connector wiring is solved before the facade stack and routing
  are stable

## Current Source Of Truth

- Repo overview: `/Users/sereja/Projects/families/telegram/telegram-digest/telegram-mcp/README.md`
- Facade design: `/Users/sereja/Projects/families/telegram/telegram-digest/telegram-mcp/docs/superpowers/specs/2026-04-17-telegram-app-facade-design.md`
- Facade implementation plan: `/Users/sereja/Projects/families/telegram/telegram-digest/telegram-mcp/docs/superpowers/plans/2026-04-17-telegram-dialog-facade-implementation.md`
