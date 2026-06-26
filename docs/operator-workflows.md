# Power Mode And Operator Workflows

The current local owner setup uses `owner_local_full_mcp`. The repository also
keeps a restricted facade profile and broader operator workflows. These modes
must stay explicit because they differ in how much Telegram state they can read
or change.

Unified workflow for users:
- Default owner path: local full MCP on explicit owner accounts.
- Restricted path: Telegram facade profile for read/search/context/draft work.
- Non-default path: direct Telethon is operator/debug only.

## Owner Local Full MCP

Owner local full MCP is the normal local plugin path in this repository. It
exposes the full Telegram MCP surface on explicit owner accounts and relies on
local operator discipline, bearer auth, and control-plane checks.

This boundary is runtime-enforced when these controls are kept intact:

- MCP daemon runs with unset/default/full profile for the owner local full
  surface, or with an explicit account-specific launchd config.
- HTTP/SSE daemon transport has `TELEGRAM_MCP_AUTH_TOKEN` configured in both
  server and client.
- Plugin MCP config stays on `plugin/.mcp.json` without legacy `allowedTools`
  allowlists.
- Control-plane policy stays on `owner_local_full_mcp`.

## Facade Profile

Facade profile is the restricted compatibility path. It supports live
read/search/context, non-sending drafts and previews, scoped local media
download, and selected voice/video transcription.

Facade profile should be safe to try without the agent sending messages,
changing chats, changing profile state, or launching background mirror/archive
jobs.

Enable it intentionally:

```bash
cd mcp
TELEGRAM_MCP_TOOL_PROFILE=facade .venv/bin/telegram-mcp
```

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
`plugin/.mcp.full.example.json` as a wildcard client-config starting point.

Power Mode is enforced by explicit operator choice and local client config.

Before using Power Mode:

- verify owner-local full MCP status first;
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
owner-local full MCP and facade profile.

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
jobs into facade tools.

## Telecrawl Archive

Telecrawl-style archives are historical search aids. They can find candidate
messages across archive coverage, but a negative result means only "not found in
this archive coverage".

Before relying on archive evidence, check account readiness, coverage,
freshness, and known import gaps.

## Subscriber Export

Subscriber/member export is sensitive and can produce PII-heavy local artifacts.
It is not part of the facade profile.

Use subscriber export only with explicit user intent, private local output
paths, and clear reporting of `visible_count`, `exported_count`, `missing`, and
completeness caveats. Do not treat a single `get_participants` slice as a full
export.
