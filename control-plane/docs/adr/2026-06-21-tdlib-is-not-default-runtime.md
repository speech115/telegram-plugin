# ADR: TDLib is not the default Telegram runtime

Status: accepted
Date: 2026-06-21

## Context

The local Telegram stack already has a single owner runtime: `telegram-mcp`.
That runtime owns user-account sessions, Telethon access, MCP tools, telemetry,
cache behavior, and media/download policy. The `tools/telegram` repository is
the control-plane around that runtime: policy, audits, remediation plans,
surface contracts, and operator documentation.

Telegram TDLib is a full Telegram client engine, not a thin helper library. It
brings its own authorization state, encrypted local database, file database,
update loop, and JSON/C bridge. Adding it as a sidecar would create a second
client runtime with a separate source of truth for sessions, local state, files,
and updates.

Recent telemetry points to operational issues in the current runtime:
preflight violations, tool contract/type errors, and slow media paths. Those
signals do not prove that Telethon is the limiting layer.

## Decision

Do not add TDLib as the default runtime, sidecar, or roadmap dependency for the
control-plane.

Keep `telegram-mcp` + Telethon as the only owner runtime for user-account
access. New Telegram capabilities should be implemented as task-shaped tools in
the existing MCP runtime first.

TDLib is allowed only as an isolated lab proof of concept when there is a
specific, measured Telethon limitation that cannot be fixed inside the current
runtime.

## TDLib POC gate

A TDLib proof of concept must be:

- read-only;
- isolated from existing Telethon session files;
- limited to one account and one scenario;
- backed by a dedicated database and files directory;
- measured against the current `telegram-mcp` path with the same input data;
- excluded from default routing, LaunchAgents, release gates, and installed
  plugin docs until the gate passes.

Valid initial scenarios are:

- global message search quality or latency;
- sent-media search quality or latency;
- media download latency or resumability.

Kill the POC if any of these happens:

- it requires sharing or converting current Telethon session files;
- authorization, database encryption, or update-loop code becomes the main work;
- it does not provide a clear measured advantage over the current runtime;
- read behavior diverges from `telegram-mcp` in a way that agents would need to
  understand;
- it requires new persistent daemon management before proving value.

## Consequences

The next practical improvements stay Telethon-first:

- reduce preflight violations in the existing MCP flow;
- fix `get_me` and tool contract/type error buckets;
- improve media download repeat behavior using the existing download registry,
  cache, and concurrency controls;
- benchmark `global_search` and `sent_media_search` before considering a new
  backend.

This keeps one session owner, one telemetry stream, and one policy surface.
