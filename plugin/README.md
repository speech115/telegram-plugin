# Telegram local plugin

This plugin gives Codex a Telegram-flavored front door backed by the local
`telegram-mcp` daemon at `http://127.0.0.1:8799/mcp`.

The default installed surface is Default Mode: read-only and preview tools for
live dialog resolution, reading, searching, context collection, scoped media,
voice transcription, and non-sending reply drafts.

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

Power Mode and Operator Workflows still exist in the broader local Telegram
stack, but they require explicit non-default tooling and their own safety
checks. Media download and voice transcription are scoped local inspection tools
in the default allowlist.

Right now this is the practical middle ground: Gmail-like plugin UX around the
live Telegram MCP, without pretending we already have a first-class app
connector id.
