# MCP Surface

Default local agent surface is the full `telegram-mcp` tool set.
The active policy profile is `owner_local_full_mcp` in
`policy/surface-contract.json`.

The old 16-tool facade allowlist is no longer the healthy target for this
single-user machine. A healthy config exposes the local MCP server without
`allowedTools`/`allowTools`, so agents can use reads, writes, media, contacts,
groups, reactions, pins, polls, stories, privacy and profile tools directly.

Expected high-value tools include `telegram_read`, `telegram_search`,
`global_search`, `sent_media_search`, `list_forum_topics`,
`get_forum_topics_by_id`, `get_discussion_message`, `get_thread_replies`,
`get_message_reactions`, `get_unread_reactions`, `telegram_send`,
`send_message`, `edit_message`, `delete_messages`, `forward_messages`,
`set_message_pinned`, `send_reaction`, `send_file`, `list_chats`, and
`list_contacts`.

`sent_media_search` is intentionally bounded by recent dialogs via `max_dialogs`.
This keeps the tool fast and avoids Telegram API sent-media filters that are not
accepted consistently for user accounts.

Owner account daemons are intentional:

- `telegram-main` / `telegram-crwddy` -> `http://127.0.0.1:8799/mcp`
- `telegram-recklessou` -> `http://127.0.0.1:8801/mcp`
- `telegram-teamsyncsage` -> `http://127.0.0.1:8802/mcp`
- `telegram-vermassov` -> `http://127.0.0.1:8803/mcp`

The legacy `telegram-pl` daemon on `8800` may also exist. Do not use any account
port as silent failover for another: each port is a different Telegram account.
Pick the account explicitly.

## Naming note

- `telegram-release-gate` **runs** the bundled pre-release gates.
- `telegram-release-gates` **audits** the gate configuration only.
