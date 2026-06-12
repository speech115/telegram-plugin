# Telegram Control Plane

Operator control-plane for the local Telegram stack.

This is not a monorepo migration and not a new source of truth. It observes the
existing live components and fails closed when their state disagrees with the
desired policy.

## Quick Start

```bash
./bin/tgc next --json       # doctor triage as prioritized actions with exact commands
./bin/tgc commands --json   # machine-readable registry of every command
./bin/telegram-status --json
./bin/telegram-doctor --json
./bin/telegram-maintenance-doctor --json
```

`tgc` is the agent entrypoint: `next` answers "what should I do right now",
`commands` lists every public command with purpose, level
(daily/live/mirror/drilldown/maintenance/release), and safety class. The
registry is unit-tested against `bin/`, so it cannot drift.

Use `telegram-status`/`telegram-doctor` for quick local health. They run the
single-user core profile by default. For low-stakes current reads, use the live
Telegram path instead:

```bash
tg read today <chat> --limit 30 --json
```

For local mirror work, use the mirror fast path/status first; full mirror
promotion, export completeness, and recovery checks belong to maintenance.

```bash
./bin/telegram-mirror-fast status --json
./bin/telegram-mirror-fast read <channel-or-chat> --limit 30 --json
./bin/telegram-mirror-fast search <text> --target <channel-or-chat> --limit 30 --json
```

Run component commands such as `telegram-mcp-surface`,
`telegram-telemetry-status`, `telegram-telecrawl-status`, `telegram-docs-audit`,
or `telegram-managed-systems` only as drill-down after a core or maintenance
check points at that component. `telegram-release-gate` is the release path, not
the daily path.

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

After rebuilding the package, materialize Codex's local plugin cache only as an
explicit maintenance/release step:

```bash
codex plugin remove telegram@sereja-local && codex plugin add telegram@sereja-local
./bin/telegram-plugin-drift --json
./bin/telegram-mcp-surface --json
```

## Human Entry Points

- `MAP.md` explains where every Telegram-related system lives.
- `PLAN.md` records the current control-plane rollout strategy.
- `PROTECTION.md` defines the cleanup and deletion safety contract.
- `docs/telegram-kit-explainer.html` is a self-contained Russian explainer for
  how the Telegram agent kit fits together (open locally in a browser).

`telegram-doctor --json` writes the runtime-only core-profile
`generated/observed-registry.json` snapshot and exits non-zero while blocking
defects are present. The snapshot is intentionally ignored by git because it
contains live PIDs, timestamps, and host inventory state.

Use `telegram-doctor --profile maintenance --json` or
`telegram-maintenance-doctor --json` for the broad estate audit that includes
release, plugin, archive, telemetry, and recovery checks.

`telegram-repair-plan --json` is dry-run planning only. It describes ordered
repair steps, touched paths, verification commands, and rollback notes without
applying changes.

`telegram-repair-plan-apply --json` runs only allowlisted safe apply steps (today:
`plugin-cache-materialize` when drift reports installer-ready cache lag). Do not
run it from a general status/read task.

`telegram-telemetry-status --json` summarizes daily JSONL logs, checks Prometheus
`/metrics` targets (9109/9110), and applies thresholds from
`policy/telemetry/alert-thresholds.json`. Import `policy/telemetry/grafana-dashboard.json`
into Grafana and include `policy/telemetry/prometheus-scrape.yml` in Prometheus.

## Surface Contract

The default Telegram MCP endpoint is read-mostly toward external Telegram state.
It may resolve, read, search, collect context, prepare send/reply previews, and
perform confirmed sends through `telegram_confirmed_send` after a fresh preview
token. It must not expose raw send/reply, edit, delete, mark, create, invite,
promote, or other direct mutation tools.

Write-capable tools such as `send_dialog_message`, `reply_in_dialog`, and
`reply_message` are allowed only in an explicit `full` or `admin` tool profile.
The control-plane treats any raw write-capable tool in the default profile or
plugin allowlist as a blocking defect. `telegram_confirmed_send` is the approved
confirmed-write facade tool.

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

Gate order and commands are defined in `policy/release-gates.json`; the shell
entrypoint is a thin wrapper over `telegram_control_plane.release_gate`.

Local mode runs managed-systems, MCP surface, plugin drift, docs audit, unit
tests, and live smokes. Use `./bin/telegram-release-gate --ci` in GitHub Actions
(agent-docs check, docs audit, pytest only). Integration smokes stay manual:
`python3 -m pytest -q -m integration`.

`telegram-maintenance-doctor` includes the docs audit via the `docs` registry
component.

## Command Levels

- Daily: `telegram-status`, `telegram-doctor`.
- Live read: `tg read today <chat> --limit 30 --json`.
- Mirror fast path: `telegram-mirror-fast status/read/search`; full mirror
  preflight is maintenance only.
- Drill-down: component audits such as `telegram-mcp-surface`,
  `telegram-telemetry-status`, `telegram-telecrawl-status`,
  `telegram-managed-systems`, and `telegram-docs-audit`.
- Release/maintenance: `telegram-maintenance-doctor`, `telegram-release-gate`,
  `telegram-agent-docs-sync`, `telegram-install-adapters`, plugin cache
  materialization, `telegram-repair-plan`, and `telegram-repair-plan-apply`.

## Current Status

- Healthy core target: `telegram-doctor --json` returns `ok` with
  `0` blocking findings and does not run release/archive/telemetry checks.
- Healthy maintenance target: `telegram-maintenance-doctor --json` returns
  `warn` with `0` blocking findings; any blocking finding is a release blocker
  (`exit 1`).
- A maintenance `warn` with `0` blocking findings is an operational warning, not
  a reason to start repair. Read `findings[].component` first, then run
  `telegram-repair-plan --json` only when a concrete repair is needed.
- Expected maintenance warning: `telecrawl_known_gaps` when the default archive
  still has retryable import gaps (`TimeoutError` backlog). This is documented
  in `policy/telecrawl.json` and is not a core/live Telegram blocker.
- Expected maintenance warning: `mcp_telemetry` when recent tool errors or error
  rate cross local telemetry thresholds. Check `telegram-telemetry-status --json`
  before changing runtime routing.
- `telegram-fast-read-today me --limit 1` is the local fast smoke for the
  supported simple-read shortcut.
- `telegram-managed-systems --json` is the canonical inventory of Telegram
  source repos, plugin/skill surfaces, runtime data roots, and archive tools.
  A missing blocking-protected path is a fail-closed defect.
- Portable plugin package, marketplace alias, live skill, and installed cache are
  aligned at local Telegram plugin version `0.1.10`.
- The default MCP tool profile is the restricted facade profile. Admin/channel
  management tools require an explicit full/admin profile.
- `telegram-mcp-surface --json` may report the broader live backend tool count;
  that is not drift by itself. The default profile is healthy when the approved
  16 facade tools are the only `default_surface_tools` and
  `unexpected_write_or_destructive_tools` is empty.
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
- For any doctor warning that looks actionable, run
  `./bin/telegram-repair-plan --json` and inspect the dry-run before applying
  anything.
- Do not run plugin cache materialization, adapter installs, docs sync restarts,
  or `telegram-repair-plan-apply` without an explicit maintenance/release task.
- Do not start mirror watchers, backfills, sync jobs, or LaunchAgents.
- Do not copy Telegram sessions into this tree.
- Do not store secrets, session strings, subscriber exports, media payloads, or
  raw private errors in policy/registry files.
