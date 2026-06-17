# Telegram local plugin

Local single-user Telegram MCP package for Codex/Claude agents. This is not an
official Telegram client or Telegram LLC distribution.

The plugin points agents at two local `telegram-mcp` HTTP daemons:

- `telegram-main` -> `http://127.0.0.1:8799/mcp`
- `telegram-pl` -> `http://127.0.0.1:8800/mcp`

Both expose the full local Telegram tool surface. The package intentionally does
not write `allowedTools`; the owner wants agents to use Telegram directly and
quickly through MCP.

For normal current/live tasks, use MCP first:

- read/search: `telegram_read`, `telegram_search`, `list_chats`, `list_contacts`
- send: `telegram_send` or `send_message`
- mutate: `edit_message`, `delete_messages`, `forward_messages`,
  `set_message_pinned`, `send_reaction`
- media/files: `telegram_inspect_media`, `download_media`, `send_file`

`telegram-confirmed` preview tools still exist as optional workflow helpers, but
they are no longer the default route for this local owner setup.

Do not treat `8800` as failover for `8799`: it is a second account. Pick
`telegram-main` or `telegram-pl` explicitly.
