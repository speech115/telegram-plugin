# Telegram local plugin

Community-maintained packaging for local use. This is not an official Telegram
client or Telegram LLC distribution.

## Codex: read a chat (8 lines)

For «что нового» / today / recent — **do not** explore mcporter or this README first.

```bash
tg read today <chat> --limit 30 --json
```

Then: `telegram-fast-read-today` → MCP `telegram_read` `mode="fast"`. Skill routing:
`skills/telegram/references/facade-routing.md` (Codex entry card). Install `tg`:
`tools/telegram/bin/telegram-kit --local`.

---

This plugin gives Codex a Telegram-flavored front door backed by the local
`telegram-mcp` daemon at `http://127.0.0.1:8799/mcp`.

Recommended onboarding path is plugin source -> marketplace/cache
materialization -> parity check -> first live facade smoke. Manual `.mcp.json`
copying is fallback-only when plugin install/materialization is unavailable.

The default installed surface is Default Mode: read-only and preview tools for
live dialog resolution, reading, searching, context collection, scoped media,
voice transcription, and non-sending reply drafts.

Default Mode boundaries are enforced by runtime profile + plugin allowlist
(`TELEGRAM_MCP_TOOL_PROFILE=default` and `plugin/.mcp.json`). HTTP daemon mode
also requires a local bearer token (`TELEGRAM_MCP_AUTH_TOKEN`) configured on the
server and client. The plugin MCP config references that variable with
`bearer_token_env_var`; it does not store the token itself.

What it does:

- packages Telegram dialog skills and starter prompts into one installable plugin
- points Codex at the live `telegram-mcp` server instead of mirror-first routing
- exposes only the Default Mode facade allowlist for read/search/context/draft
  work
- keeps the plugin ready for a future real app binding if a `connector_...` or `asdk_app_...` id is provisioned later

What it does not do yet:

- it does not expose write, subscriber export, or admin tools in the default
  plugin allowlist
- it does not mint a real `app://telegram` id locally
- it does not replace platform-side app provisioning

Unified workflow: use Default Mode facade tools first for normal user tasks.
Use Power Mode only when the user explicitly requests write/admin operations.
Direct Telethon usage is not a normal user path; keep it for operator/debug
workflows.

Power Mode and Operator Workflows still exist in the broader local Telegram
stack, but they require explicit non-default tooling and their own safety
checks. Media download and voice transcription are scoped local inspection tools
in the default allowlist.

Right now this is the practical middle ground: Gmail-like plugin UX around the
live Telegram MCP, without pretending we already have a first-class app
connector id.
