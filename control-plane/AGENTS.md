# Telegram Control-Plane Rules

- This directory is the local Telegram control-plane, not a Telegram runtime repo.
- Default operation is read-only toward external Telegram components.
- Do not move repos, refresh plugin cache, sync skill-index, rewrite LaunchAgents,
  start mirror jobs, or copy sessions from here without an explicit later plan.
- `generated/` may be rewritten by local doctor/status commands.
- The first milestone is allowed to fail closed on known defects.

## Agent Entry (read this first)

### Codex (live read — hot path)

Do **not** load the full telegram skill for «что нового / прочитай чат за сегодня».

1. `tg read today <chat> --limit 30 --json`
2. Fallback only if that fails: MCP `telegram_read` with `mode="fast"`.
3. If intent/routing is unclear, read `telegram://docs/routing`.
4. Forbidden until read fails: mcporter, tool_search, plugin README, doctor, launchd.

`tg` on PATH: `./bin/telegram-kit --local`

### All hosts

For live Telegram work, read MCP resources first (smaller than the full skill):

- `telegram://docs/routing`, `telegram://docs/tools`, `telegram://docs/sources`

Full skill: `$HOME/.agents/skills/telegram` (symlink to
`generated/telegram-plugin-package/skills/telegram`). Do not improvise Telethon
calls or browse `telegram-mcp` unless debugging.

### Speed path (low-stakes "что нового / за сегодня")

1. Classify: current/today/recent → **live only** (never mirror/archive).
2. On this host, run first:
   `tg read today <chat> --limit 30 --json`.
3. If that fails, call MCP `telegram_read` with `mode="fast"`, not legacy
   `read_today_dialog` (not on default allowlist).
4. Skip `mcporter list`, doctor, launchd, and plugin README until a real failure.

### Quality path (complete / media / send)

| User intent | Tool | Notes |
| --- | --- | --- |
| Keyword in dialog | `telegram_search` | Then fetch context only for hits |
| Full today, nothing missed | `telegram_read` `mode="full"` + page | Report `truncated` / `has_more_before` |
| Draft reply | `telegram_prepare_reply` | No send without explicit user text |
| Send | `telegram_confirmed_send` | Fresh `confirmation_token` from preview |
| Photos/video | `telegram_inspect_media` / downloads | Never answer from captions only |
| Historical (allowlist) | `telegram-local-mirror` skill | Not for today/latest |

### Default MCP surface (16 tools)

Only these are exposed to agents via plugin allowlist: `telegram_read`,
`telegram_search`, `telegram_prepare_reply`, `telegram_confirmed_send`,
`telegram_inspect_media`, `telegram_export_members`, `resolve_dialog`,
`find_dialog`, `collect_dialog_context`, `collect_context`, `download_media`,
`download_media_batch`, `download_dialog_media`, `prepare_media_inspection_manifest`,
`get_me`, `doctor_check`. Legacy aliases (`read_today_dialog`, `prepare_dialog_reply`,
`draft_reply`, `search_dialog_messages`, …) and raw `send_dialog_message` /
`reply_in_dialog` are **not** on the default surface (full/admin profile only).

If `telegram-mcp-surface --json` reports a larger backend `tool_count`, do not
treat that alone as drift. The default profile is healthy when
`default_surface_tools` matches these 16 approved tools and
`unexpected_write_or_destructive_tools` is empty.

### Doctor warn triage

Use doctor for control-plane health, not for ordinary live reads. Interpret
`./bin/telegram-doctor --json` by severity, not by the top-level word alone.
`telegram-doctor` is the fast core profile by default; use
`./bin/telegram-maintenance-doctor --json` or
`./bin/telegram-doctor --profile maintenance --json` only for broad
release/archive/recovery checks:

1. `status=ok`: control-plane checks are clean.
2. `status=warn` with `summary.blocking_findings=0`: operational warning, not a
   release blocker. Read `findings[].component` before acting.
3. `status=fail` or any blocking finding: stop and use
   `./bin/telegram-repair-plan --json` before proposing changes.

Common non-blocking maintenance warnings:

- `mcp_telemetry`: recent MCP tool errors or high error rate. Check
  `./bin/telegram-telemetry-status --json`; do not rewrite runtime routing from
  this signal alone.
- `telecrawl_known_gaps`: archive import backlog or terminal archive gaps.
  Telecrawl is archive evidence, not live/current Telegram truth.
- `plugin_cache_needs_materialization`: plugin/cache install lag. This is
  distinct from default MCP surface health.

Surface health and maintenance health are separate layers: a green
`telegram-mcp-surface --json` can coexist with maintenance `warn`, and plugin
drift can be green while another runtime layer warns.

### Operator command levels

- Daily health: `./bin/telegram-status` for a human summary, or
  `./bin/telegram-doctor --json` for machine-readable core output.
- Mirror fast path: use `./bin/telegram-mirror-fast status/read/search` first
  when the task explicitly asks for mirror; it reads local export/ledger files
  only. Mirror promotion/preflight is maintenance, not daily mirror use.
- Drill-down: run `telegram-mcp-surface`, `telegram-docs-audit`,
  `telegram-telemetry-status`, `telegram-telecrawl-status`, or other component
  checks only after doctor points at that component.
- Maintenance/release: `telegram-maintenance-doctor`, `telegram-release-gate`,
  plugin cache materialization, adapter installs, and docs sync require an
  explicit maintenance/release task.

### Doc sync (skill ↔ MCP resources)

Edit `generated/telegram-plugin-package/skills/telegram/references/`, then:

```bash
./bin/telegram-agent-docs-sync
```

Restarts local MCP HTTP daemons automatically after sync. CI uses `--check --no-restart`.
`build-plugin-package` runs the same sync automatically. Manifest:
`skills/telegram/agent-docs/manifest.json`.

### Telemetry (local)

- Daily JSONL: `~/telegram-mcp/telemetry/daily/YYYY-MM-DD.jsonl` (30-day retention).
- Symlink: `~/telegram-mcp/telemetry.jsonl` → today’s file.
- Snapshot: `~/telegram-mcp/telemetry-stats.json` (runtime_stats + scheduler, ~60s).
- Prometheus: `http://127.0.0.1:9109/metrics` (set `TELEGRAM_TELEMETRY_METRICS_PORT`; use `9110` for PL profile).
- Policy: `policy/telemetry/` (Prometheus scrape, alert rules, Grafana dashboard JSON).
- Summarize: `./bin/telegram-telemetry-status --json` or MCP `bin/telemetry-summary --json`.
- Event `source`: `mcp_tool`, `fast_read_cli`, `mcp_server` — only paths through MCP/fast-read are tracked.
- `doctor_check` includes `telemetry_summary` for the last 24h.

### Verification on this host

```bash
tg read today me --limit 1 --json
./bin/telegram-status
./bin/telegram-doctor --json
```

Fast read must return `payload.data_source == "live_telegram"`, not
`Unknown tool`. Use `./bin/telegram-golden-read-smoke --json` only for release
or live-smoke verification; it covers five dialogs in `policy/golden-dialogs.json`
(me, Конспекты, three DMs). Use `TELEGRAM_GOLDEN_READ_SKIP=1` only in CI/offline.

### Runtime locations

- Live MCP backend: `policy/managed-systems.json` → `telegram-mcp`
- Portable plugin: `generated/telegram-plugin-package`
- Human map: `MAP.md`, roadmap: `TELEGRAM_AGENT_KIT_ROADMAP.md`

## Agent skills

### Issue tracker

Issues and PRDs live as markdown under `.scratch/<feature-slug>/`. See `docs/agents/issue-tracker.md`.

### Triage labels

Five canonical triage roles (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`) map 1:1 to `Status:` lines in local issue files. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context layout: `CONTEXT.md` at the repo root and `docs/adr/` for decisions. See `docs/agents/domain.md`.
