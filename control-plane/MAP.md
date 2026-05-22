# Telegram Tooling Map

Start here when working on local Telegram tooling.

## Main Entry

- `${TELEGRAM_CONTROL_PLANE_ROOT:-./control-plane}`
  - role: control-plane, protection layer, generated observer registry
  - use for: status, doctor, managed inventory, repair planning
  - do not store: sessions, secrets, raw media, archive DBs, subscriber exports

## Live Telegram

- `${TELEGRAM_MCP_REPO:-./mcp}`
  - role: live MCP backend
  - use for: current Telegram reads, dialog facade, live MCP daemon code
  - protected by: `telegram-plugin-drift`, `telegram-mcp-surface`,
    `telegram-mcp-profiles`, `telegram-launchd-audit`

## User-Facing Plugin And Skills

- `${TELEGRAM_PLUGIN_SOURCE:-./plugin}`
  - role: local Telegram plugin source
  - use for: plugin package metadata, MCP allowlist, assets, user-facing skill

- `${TELEGRAM_PLUGIN_CACHE_ROOT:-~/.codex/plugins/cache/sereja-local/telegram}`
  - role: installed plugin cache
  - use for: installed/cached plugin parity checks

- `${TELEGRAM_LIVE_SKILL:-~/.agents/skills/telegram}`
  - role: live Telegram skill facade
  - use for: normal live dialog work, media/voice inspection, draft/send flows

- `${TELEGRAM_LOCAL_MIRROR_SKILL:-~/Projects/.codex/skills/telegram-local-mirror}`
  - role: archive/mirror routing skill
  - use for: allowlisted mirror reads and telecrawl archive search guidance

## Mirror

- `${TELEGRAM_CONTROL_PLANE_ROOT:-./control-plane}-mirror`
  - role: mirror recovery candidate
  - current classification: `mirror-recovery`
  - use for: mirror source inspection, recovery work, preflight only
  - do not do from this control-plane: start watchers, backfills, sync jobs, or
    promote to runtime without `telegram-mirror-preflight --json`

- `${TELEGRAM_MIRROR_LEGACY_ALIAS:-~/Projects/tools/telegram-mirror}`
  - role: legacy compatibility symlink
  - use for: discovery and old references only

## Telecrawl

- `${TELECRAWL_ARTIFACT_ROOT:-~/Projects/.artifacts/telecrawl}`
  - role: account-scoped archive DBs, manifests, logs
  - use for: historical archive evidence and gap accounting
  - not live/current truth

- `${TELECRAWL_HOME:-~/.telecrawl}`
  - role: local telecrawl runtime/user state

- `${TELECRAWL_ARCHIVE_BIN:-telecrawl-archive}`
  - role: archive CLI wrapper

- `${TELECRAWL_FAST_BIN:-telecrawl-fast}`
  - role: patched import binary

## Cleanup Rule

Do not delete Telegram-related paths directly. First run:

```bash
./bin/telegram-managed-systems --json
./bin/telegram-doctor --json
./bin/telegram-repair-plan --json
```

Then use a dry-run cleanup plan, recoverable safe-trash or backup, and explicit
approval before any stateful action.
