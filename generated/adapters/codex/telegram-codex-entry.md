# Codex: Telegram live read hot path

Do not load the full telegram skill for «что нового» / read chat today.

## Run first

```bash
tg read today <chat> --limit 30 --json
```

Fallbacks (stop on first success): `telegram-fast-read-today` → MCP `telegram_read` mode=fast limit≤30.

Optional: MCP resource `telegram://docs/routing` (5 lines). Not this file on every turn.

## Forbidden before read succeeds

- mcporter / MCP server discovery
- tool_search for how to read Telegram
- plugin README, doctor_check, launchd
- @telegram bootstrap for a simple read
- mirror / telecrawl for today/latest

## After read

Reuse `chat.dialog_ref`. Sends are direct when the user gave an explicit target
and exact text: prefer `telegram_send` / `send_message`. Use preview/confirmed
tools only when the user asks to preview first.

Install tg: tools/telegram/bin/telegram-kit --local
