# Telegram API Agent Roadmap

Status: ready-for-agent

## Goal

Expand the local Telegram MCP so AI agents can find context across Telegram, preserve thread/topic context, inspect reactions, and track official Telegram API gaps without adding unsafe write capabilities by default.

## Scope

Must add:
- `global_search`: search across chats, not only inside one dialog.
- `thread_context`: replies, discussion, and topic-aware reads.
- `reaction_analytics`: reaction lists, unread reactions, and read-reaction support.
- `sent_media_search`: find sent photos, videos, documents, and other media quickly.
- Primary docs cleanup: hide legacy aliases from primary agent-facing docs; keep compatibility aliases available.

Should add:
- `forum_tools`: forum topic listing, replies, discussion message, read discussion.
- `story_analytics`: first-class story views, reactions, viewers, and deep links.
- `business_audit`: read-only inventory of connected bots and business capabilities before any business writes.
- `docs_gap_audit`: compare official Telegram API changelog/methods against MCP surface.

Out of scope for this phase:
- Pyrogram migration.
- Full TDLib rewrite.
- TDLib sidecar/default runtime unless an isolated read-only POC passes the ADR
  gate in `docs/adr/2026-06-21-tdlib-is-not-default-runtime.md`.
- Stars, gifts, paid media writes.
- Business write-actions without a separate permission model.
- Mini Apps UI.

## Safety Model

Default work starts with read-only tools. Mutating tools require explicit surface-contract review and tests. Business operations start with read-only audits only.

## Success Criteria

- New tools are registered in full surface and, where safe, facade surface.
- Registration tests and surface-contract tests pass.
- Each new tool has unit tests around result shape and basic parameter handling.
- Live-smoke path remains read-only unless explicitly requested.
- Docs clearly distinguish owner-local user-account tools from Bot API/business-bot capabilities.
