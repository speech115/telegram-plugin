# Telegram Tooling Map

Start here when working on local Telegram tooling.

## Main Entry

- `/Users/sereja/Projects/tools/telegram`
  - role: control-plane, protection layer, generated observer registry
  - use for: status, doctor, managed inventory, repair planning
  - do not store: sessions, secrets, raw media, archive DBs, subscriber exports

## Live Telegram

- `/Users/sereja/Projects/families/telegram/telegram-digest/telegram-mcp`
  - role: live MCP backend
  - use for: current Telegram reads, dialog facade, live MCP daemon code
  - protected by: `telegram-plugin-drift`, `telegram-mcp-surface`,
    `telegram-mcp-profiles`, `telegram-launchd-audit`

## User-Facing Plugin And Skills

- `/Users/sereja/plugins/telegram`
  - role: local Telegram plugin source
  - use for: plugin package metadata, MCP allowlist, assets, user-facing skill

- `/Users/sereja/.codex/plugins/cache/sereja-local/telegram`
  - role: installed plugin cache
  - use for: installed/cached plugin parity checks

- `/Users/sereja/.agents/skills/telegram`
  - role: live Telegram skill facade
  - use for: normal live dialog work, media/voice inspection, draft/send flows

- `/Users/sereja/Projects/.codex/skills/telegram-local-mirror`
  - role: archive/mirror routing skill
  - use for: allowlisted mirror reads and telecrawl archive search guidance

## Mirror

- `/Users/sereja/Projects/tools/telegram-mirror`
  - role: mirror recovery candidate
  - current classification: `mirror-recovery`
  - use for: mirror source inspection, recovery work, preflight only
  - do not do from this control-plane: start watchers, backfills, sync jobs, or
    promote to runtime without `telegram-mirror-preflight --json`

- `/Users/sereja/Projects/tools/hermes-agent-local/workspace/integrations/telegram-mirror`
  - role: legacy compatibility symlink
  - use for: discovery and old references only

## Telecrawl

- `/Users/sereja/Projects/.artifacts/telecrawl`
  - role: account-scoped archive DBs, manifests, logs
  - use for: historical archive evidence and gap accounting
  - not live/current truth

- `/Users/sereja/.telecrawl`
  - role: local telecrawl runtime/user state

- `/Users/sereja/Projects/tools/agent-tooling/bin/telecrawl-archive`
  - role: archive CLI wrapper

- `/Users/sereja/Projects/tools/agent-tooling/bin/telecrawl-fast`
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

