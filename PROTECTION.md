# Telegram Protection Contract

This directory is the canonical index for local Telegram tooling. It protects
systems by registering where they live; it does not absorb their private state.

## Deletion Rule

Do not delete, move, archive, or rewrite Telegram-related paths directly.

Before any cleanup:

1. Run `./bin/telegram-managed-systems --json`.
2. Run `./bin/telegram-doctor --json`.
3. Produce a dry-run repair or cleanup plan listing touched paths.
4. Use recoverable safe-trash or a timestamped backup path.
5. Get explicit user approval for the stateful action.

## Managed Inventory

`policy/managed-systems.json` is the source of truth for Telegram-related
source repos, plugin/skill surfaces, runtime data roots, and archive tools.

If a blocking-protected path disappears, `telegram-doctor` must fail closed.

This is a control-plane guard, not an operating-system lock. A direct destructive
shell command can still remove files. For stateful cleanup, the required safety
mechanism is the workflow above: inventory first, dry-run plan second,
recoverable backup/safe-trash third, explicit approval last.

## What Must Not Live Here

- Telegram session strings
- Telegram Desktop `tdata`
- raw media payloads
- subscriber exports
- unredacted archive databases
- secrets or private env files
