# Threat Model

Telegram is a private, stateful messaging surface. Agent access should be
treated differently from a normal stateless API integration.

## Assets

- Telegram API credentials.
- Telethon session files and string sessions.
- Telegram Desktop `tdata`.
- Message contents, contact lists, channel membership, media, and voice files.
- Local archive databases and generated search indexes.

## Active Boundary

The current local owner setup uses `owner_local_full_mcp`: the owner-facing
plugin intentionally exposes the full local Telegram MCP surface for explicit
owner accounts. This is different from a public or semi-trusted default surface.

Full local access is allowed for the owner workflow, but sensitive tools still
need honest classification. Sending messages, deleting messages, invite-link
export, admin operations, subscriber/member export, and bulk archive jobs are
privacy- or state-changing workflows. They should be auditable, clearly
documented, and not hidden inside a routine read-only facade.

## Facade Boundary

The optional `facade`/`safe`/`restricted` profiles should expose only tools that
are safe for routine agent context gathering:

- resolve dialogs;
- read bounded message ranges;
- search messages;
- collect context;
- prepare drafts without sending;
- inspect/download scoped media locally;
- transcribe voice locally through Telegram-supported runtime behavior.

Subscriber/member export is intentionally available for the owner in full mode,
but it is not ordinary context gathering and should not be registered as a
read-only facade tool.

Enforcement status:

- active owner mode is enforced by `control-plane/policy/surface-contract.json`
  (`owner_local_full_mcp`);
- facade mode is enforced by MCP profile selection (`TELEGRAM_MCP_TOOL_PROFILE`
  set to `facade`, `safe`, or `restricted`);
- enforced by bearer auth on HTTP/SSE daemon transports
  (`TELEGRAM_MCP_AUTH_TOKEN`);
- still depends on local operator discipline not to replace default config with
  Power Mode examples unintentionally.

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
- Keep the owner-local full surface explicit in `surface-contract.json` and
  separate it from facade profiles.
- Keep subscriber/member export and invite-link export out of routine read-only
  facade semantics.
- Run contract smoke checks after changing MCP tools or plugin metadata.
- Use the control-plane doctor/status commands before trusting a local runtime.
- Keep mirror/archive jobs cold unless a separate runtime plan starts them.
- Review generated artifacts before publishing anything externally.
