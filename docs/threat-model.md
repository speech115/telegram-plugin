# Threat Model

Telegram is a private, stateful messaging surface. Agent access should be
treated differently from a normal stateless API integration.

## Assets

- Telegram API credentials.
- Telethon session files and string sessions.
- Telegram Desktop `tdata`.
- Message contents, contact lists, channel membership, media, and voice files.
- Local archive databases and generated search indexes.

## Default Boundary

The default plugin path should expose only tools that are safe for routine agent
context gathering:

- resolve dialogs;
- read bounded message ranges;
- search messages;
- collect context;
- prepare drafts without sending;
- inspect/download scoped media locally;
- transcribe voice locally through Telegram-supported runtime behavior.

Sending messages, deleting messages, admin operations, subscriber export, and
bulk archive jobs are separate workflows. They should require explicit user
intent and their own checks.

## Main Risks

- Prompt injection from chat messages or file names.
- Accidental disclosure of private chat content in logs, reports, or commits.
- Committing session files, archive databases, downloaded media, or `.env`.
- Confusing stale archive data with live Telegram state.
- Tool drift where a plugin exposes broader MCP tools than intended.
- Background jobs that keep reading or writing Telegram state after the user
  expects the task to be finished.

## Controls

- Keep credentials and sessions outside the repo.
- Use the plugin allowlist as the user-facing default surface.
- Run contract smoke checks after changing MCP tools or plugin metadata.
- Use the control-plane doctor/status commands before trusting a local runtime.
- Keep mirror/archive jobs cold unless a separate runtime plan starts them.
- Review generated artifacts before publishing anything externally.
