# MCP Surface

Default local agent surface is the full `telegram-mcp` tool set.

The old 16-tool facade allowlist is no longer the healthy target for this
single-user machine. A healthy config exposes the local MCP server without
`allowedTools`/`allowTools`, so agents can use reads, writes, media, contacts,
groups, reactions, pins, polls, stories, privacy and profile tools directly.

Expected high-value tools include `telegram_read`, `telegram_search`,
`telegram_send`, `send_message`, `edit_message`, `delete_messages`,
`forward_messages`, `set_message_pinned`, `send_reaction`, `send_file`,
`list_chats`, and `list_contacts`.

Two account daemons are intentional:

- `telegram-main` -> `http://127.0.0.1:8799/mcp`
- `telegram-pl` -> `http://127.0.0.1:8800/mcp`

Do not use port `8800` as silent failover for `8799`: it is a different
Telegram account. Pick the account explicitly.

## Naming note

- `telegram-release-gate` **runs** the bundled pre-release gates.
- `telegram-release-gates` **audits** the gate configuration only.
