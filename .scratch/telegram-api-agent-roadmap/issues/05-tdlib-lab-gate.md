# TDLib Lab Gate

Status: ready-for-human

## Problem

TDLib was considered as a possible way to improve Telegram search, cache, and
media behavior. The architecture review found that TDLib is a full Telegram
client runtime, not a small helper library, and would add a second auth/session
and local-database surface next to the current Telethon-backed `telegram-mcp`.

## Decision

Do not add TDLib to the default roadmap. Follow
`docs/adr/2026-06-21-tdlib-is-not-default-runtime.md`.

## Acceptance Criteria

- `telegram-mcp` remains the only owner runtime for default user-account access.
- New Telegram capabilities are attempted in the Telethon-backed MCP runtime
  first.
- TDLib is only explored through an isolated read-only POC with one account, one
  scenario, separate database/files directories, and explicit benchmark data.
- No LaunchAgent, release gate, plugin docs, or default source routing points to
  TDLib before the POC gate passes.

## Candidate POC Scenarios

- Compare TDLib `searchMessages` against current `global_search`.
- Compare TDLib search/media filters against current bounded
  `sent_media_search`.
- Compare TDLib file download behavior against current `download_media` for
  repeated downloads of the same files.

## Kill Criteria

- POC requires session sharing or conversion from Telethon.
- POC requires persistent daemon management before proving value.
- POC does not beat the current path on latency, quality, or operational
  simplicity.
- POC behavior would force agents to reason about two live Telegram runtimes.
