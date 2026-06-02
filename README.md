# Telegram Control Plane

Operator control-plane for the local Telegram stack.

This is not a monorepo migration and not a new source of truth. It observes the
existing live components and fails closed when their state disagrees with the
desired policy.

## Commands

```bash
./bin/telegram-doctor --json
./bin/telegram-status --json
./bin/telegram-fast-read-today me --limit 1
./bin/telegram-managed-systems --json
./bin/telegram-plugin-drift --json
./bin/telegram-mcp-surface --json
./bin/telegram-launchd-audit --json
./bin/telegram-session-audit --json
./bin/telegram-mirror-preflight --json
./bin/telegram-telecrawl-status --json
./bin/telegram-repair-plan --json
./bin/telegram-repair-plan-apply --json
./bin/telegram-docs-audit --json
./bin/telegram-release-gates --json
./bin/telegram-install-adapters --json
./bin/telegram-release-gate
```

## Plugin Packaging

The canonical portable Telegram plugin package is:

```bash
generated/telegram-plugin-package
```

This directory is the editable package source for local materialization. The
marketplace entrypoint `/Users/sereja/plugins/telegram` is only a symlink alias
to this package root.

To build a fresh package from an independent staging source into an empty output
directory, use:

```bash
/Users/sereja/Projects/families/telegram/telegram-digest/telegram-mcp/bin/build-plugin-package \
  --source-dir /path/to/telegram-plugin-staging \
  --output-dir /path/to/empty/telegram-plugin-package \
  --json
```

`build-plugin-package` regenerates `telegram-mcp/docs/agent/` from
`skills/telegram/agent-docs/manifest.json` and skill `references/` before copying
files. To check or refresh docs without packaging:

```bash
/Users/sereja/Projects/families/telegram/telegram-digest/telegram-mcp/bin/sync-agent-docs \
  --plugin-dir /Users/sereja/Projects/tools/telegram/generated/telegram-plugin-package \
  --check --json
```

The builder fails closed if the package would contain private paths, `.env`,
`.session`, `__pycache__`, or `*.pyc` artifacts. The local marketplace still
enters through `/Users/sereja/plugins/telegram`, but that path is now a symlink
alias to the portable package root, not the canonical artifact source.

After rebuilding the package, materialize Codex's local plugin cache with:

```bash
codex plugin remove telegram@sereja-local && codex plugin add telegram@sereja-local
./bin/telegram-plugin-drift --json
./bin/telegram-mcp-surface --json
```

## Human Entry Points

- `MAP.md` explains where every Telegram-related system lives.
- `PLAN.md` records the current control-plane rollout strategy.
- `PROTECTION.md` defines the cleanup and deletion safety contract.

`telegram-doctor --json` writes the runtime-only
`generated/observed-registry.json` snapshot and exits non-zero while blocking
defects are present. The snapshot is intentionally ignored by git because it
contains live PIDs, timestamps, and host inventory state.

`telegram-repair-plan --json` is dry-run planning only. It describes ordered
repair steps, touched paths, verification commands, and rollback notes without
applying changes.

`telegram-repair-plan-apply --json` runs only allowlisted safe apply steps (today:
`plugin-cache-materialize` when drift reports installer-ready cache lag).

## Surface Contract

The default Telegram MCP endpoint is read-only toward external Telegram state.
It may resolve, read, search, collect context, and prepare send/reply previews,
but it must not send, reply, edit, delete, mark, create, invite, promote, or
otherwise mutate Telegram.

Write-capable tools such as `send_dialog_message`, `reply_in_dialog`, and
`reply_message` are allowed only in an explicit `full` or `admin` tool profile.
The control-plane treats any write-capable tool in the default profile or plugin
allowlist as a blocking defect.

For simple low-stakes "read today" tasks, `bin/telegram-fast-read-today` is the
supported first path on this host. It talks directly to the local MCP HTTP daemon
with the same bearer token env file, skips `mcporter` process/discovery overhead,
and falls back conceptually to the normal live MCP facade when unavailable. It
is read-only and must not be used for send/reply, media inspection, subscriber
export, or any workflow that needs the full facade.

`generated/observed-registry.json` is an allowlist-only runtime snapshot. It must
not contain Telegram user IDs, Telegram handles, phone numbers, exact session
paths, Telegram Desktop `tdata` paths, archive database paths, archive manifest
paths, subscriber exports, media payloads, or raw private errors.

## Release Gate

Run the bundled pre-release checks:

```bash
./bin/telegram-release-gate
```

This runs managed-systems, MCP surface, plugin drift, docs audit, and unit
tests. Use `./bin/telegram-release-gate --ci` in GitHub Actions (docs audit +
unit tests only). Integration smokes stay manual: `python3 -m pytest -q -m integration`.

`telegram-doctor` includes the docs audit via the `docs` registry component.

## Current Status

- Healthy control-plane target: `telegram-doctor --json` returns `warn` with
  `0` blocking findings; any blocking finding is a release blocker (`exit 1`).
- Expected operational warning: `telecrawl_known_gaps` when the default archive
  still has retryable import gaps (`TimeoutError` backlog). This is documented
  in `policy/telecrawl.json` and is not a release blocker.
- `telegram-fast-read-today me --limit 1` is the local fast smoke for the
  supported simple-read shortcut.
- `telegram-managed-systems --json` is the canonical inventory of Telegram
  source repos, plugin/skill surfaces, runtime data roots, and archive tools.
  A missing blocking-protected path is a fail-closed defect.
- Portable plugin package, marketplace alias, live skill, and installed cache are
  aligned at local Telegram plugin version `0.1.10`.
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
- Do not delete Telegram-related paths directly. Start from
  `policy/managed-systems.json` and create a dry-run repair/cleanup plan first.
- Do not start mirror watchers, backfills, sync jobs, or LaunchAgents.
- Do not copy Telegram sessions into this tree.
- Do not store secrets, session strings, subscriber exports, media payloads, or
  raw private errors in policy/registry files.
