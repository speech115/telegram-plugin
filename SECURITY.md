# Security Policy

This repository is a community-maintained local integration and is not an
official Telegram product channel.

## Supported Versions

This project is currently alpha software. Security fixes target the latest
commit on the default branch until tagged releases exist.

## Reporting A Vulnerability

Do not open a public issue that includes Telegram credentials, session strings,
session files, phone numbers, private chat contents, downloaded media, archive
databases, or Telegram Desktop `tdata` paths.

For now, report vulnerabilities by opening a private GitHub security advisory if
the repository settings allow it, or by contacting the maintainer directly
through the GitHub profile associated with this repository.

Include:

- affected commit or version;
- whether the issue involves Default Mode, Power Mode, control-plane,
  mirror/archive, or subscriber export;
- reproduction steps using redacted data;
- expected impact;
- suggested fix if known.

## Sensitive Data Rules

Never attach:

- `.env` files;
- Telethon `.session` files or session strings;
- Telegram Desktop `tdata`;
- raw private messages or media;
- subscriber exports;
- unredacted archive databases;
- logs containing phone numbers, user ids, handles, or exact local session paths.

Use synthetic or redacted examples instead.

## Scope

Security-sensitive areas include:

- accidental Power Mode tool exposure in the Default Mode allowlist;
- MCP runtime profile drift where `default` serves write/admin tools;
- unauthenticated local HTTP/SSE MCP endpoint exposure;
- credential/session leakage;
- prompt injection through Telegram content;
- private content leakage into generated artifacts;
- stale mirror/archive data presented as live Telegram state;
- background jobs that read or write Telegram state unexpectedly.
