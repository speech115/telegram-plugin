# Power Mode And Operator Workflows

Default Mode is intentionally safe for first install. The repository also
contains a full Telegram MCP surface and operator workflows. Those are not
second-class features; they are explicit modes because they can change Telegram
state, read in bulk, or create sensitive artifacts.

## Default Mode

Default Mode is the normal plugin path. It supports live read/search/context,
non-sending drafts and previews, scoped local media download, and selected
voice/video transcription.

Default Mode should be safe to try without the agent sending messages, changing
chats, changing profile state, or launching background mirror/archive jobs.

This boundary is runtime-enforced when both controls are kept intact:

- MCP daemon runs with `TELEGRAM_MCP_TOOL_PROFILE=default`.
- HTTP/SSE daemon transport has `TELEGRAM_MCP_AUTH_TOKEN` configured in both
  server and client.
- Plugin MCP config stays on `plugin/.mcp.json` allowlist and is not replaced by
  `plugin/.mcp.full.example.json`.

## Power Mode

Power Mode is the full MCP surface. It can expose tools that send, reply, edit,
delete, forward, react, change contacts, modify groups/channels, update profile
state, inspect stories, or change chat privacy state.

Enable it intentionally:

```bash
cd mcp
TELEGRAM_MCP_POWER_MODE=enabled TELEGRAM_MCP_TOOL_PROFILE=full .venv/bin/telegram-mcp
```

Then point a local client at the same MCP endpoint using
`plugin/.mcp.full.example.json` as a starting point.

Power Mode is enforced by explicit operator choice (runtime profile + allowlist
switch). It is not reachable through the default plugin files alone.

Before using Power Mode:

- verify Default Mode first;
- use a test chat or explicit stable target;
- keep exact message text and target identity stable;
- do not copy Power Mode allowlists into `plugin/.mcp.json`;
- expect externally visible Telegram changes.

## Operator Workflows

Operator Workflows are broader local operations around the Telegram stack:

- mirror channel/dialog runtime;
- telecrawl/archive search and coverage checks;
- subscriber/member export;
- control-plane repair, audit, and LaunchAgent/session inventory.

These workflows often involve allowlists, local databases, background jobs,
freshness checks, or PII-heavy outputs. They are intentionally separate from
Default Mode and Power Mode.

## Mirror

Mirror data is a sidecar for repeated read-heavy analysis and historical
context. It is not the authority for "latest", "today", current reply context,
media inspection, or sending.

Mirror use should be:

- allowlist-only;
- source-labeled as mirror-derived;
- freshness-checked before making current-state claims;
- kept cold unless there is a separate runtime plan.

The control-plane can audit mirror state, but it does not turn mirror runtime
jobs into Default Mode tools.

## Telecrawl Archive

Telecrawl-style archives are historical search aids. They can find candidate
messages across archive coverage, but a negative result means only "not found in
this archive coverage".

Before relying on archive evidence, check account readiness, coverage,
freshness, and known import gaps.

## Subscriber Export

Subscriber/member export is sensitive and can produce PII-heavy local artifacts.
It is not exposed in the Default Mode allowlist.

Use subscriber export only with explicit user intent, private local output
paths, and clear reporting of `visible_count`, `exported_count`, `missing`, and
completeness caveats. Do not treat a single `get_participants` slice as a full
export.
