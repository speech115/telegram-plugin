# Telegram Control Plane

Operator control-plane for the local Telegram stack.

This is not a monorepo migration and not a new source of truth. It observes the
existing live components and fails closed when their state disagrees with the
desired policy.

## Commands

```bash
./bin/telegram-doctor --json
./bin/telegram-status --json
./bin/telegram-plugin-drift --json
./bin/telegram-mcp-surface --json
./bin/telegram-launchd-audit --json
./bin/telegram-session-audit --json
./bin/telegram-mirror-preflight --json
./bin/telegram-telecrawl-status --json
./bin/telegram-repair-plan --json
```

`telegram-doctor --json` writes `generated/observed-registry.json` and exits
non-zero while blocking defects are present.

`telegram-repair-plan --json` is dry-run planning only. It describes ordered
repair steps, touched paths, verification commands, and rollback notes without
applying changes.

## Surface Contract

The default Telegram MCP endpoint is read-only toward external Telegram state.
It may resolve, read, search, collect context, and prepare send/reply previews,
but it must not send, reply, edit, delete, mark, create, invite, promote, or
otherwise mutate Telegram.

Write-capable tools such as `send_dialog_message`, `reply_in_dialog`, and
`reply_message` are allowed only in an explicit `full` or `admin` tool profile.
The control-plane treats any write-capable tool in the default profile or plugin
allowlist as a blocking defect.

`generated/observed-registry.json` is an allowlist-only persisted snapshot. It
must not contain Telegram user IDs, Telegram handles, phone numbers, exact
session paths, Telegram Desktop `tdata` paths, archive database paths, archive
manifest paths, subscriber exports, media payloads, or raw private errors.

## Current Status

- `telegram-doctor --json` is expected to return `warn` with `0` blocking
  findings and `5` warning findings while recovery/archive caveats remain.
- Plugin source and installed cache are aligned at local Telegram plugin
  version `0.1.3`; previous cache version `0.1.2` is left as rollback.
- The default MCP tool profile is the restricted facade profile. Admin/channel
  management tools require an explicit full/admin profile.
- Active MCP LaunchAgent plists no longer contain Telegram API secrets; they
  load credentials through `TELEGRAM_MCP_ENV_FILE` pointing at private `0600`
  env files under the MCP session directories.
- Legacy mirror LaunchAgent plists were moved out of `~/Library/LaunchAgents`
  and backed up under `backups/launchagents-20260522-154535/`.
- `telegram-mirror` is classified as `mirror-recovery`, not live runtime.
- `telegram-mirror-preflight --json` must be green before any promotion from
  recovery to runtime.
- `telecrawl` is classified as archive evidence, not current/live Telegram
  truth.

## Guardrails

- Do not move repos.
- Do not start mirror watchers, backfills, sync jobs, or LaunchAgents.
- Do not copy Telegram sessions into this tree.
- Do not store secrets, session strings, subscriber exports, media payloads, or
  raw private errors in policy/registry files.
