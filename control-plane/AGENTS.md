# Telegram Control-Plane Rules

This directory is the local Telegram control-plane, not a Telegram runtime repo.
Default operation is read-only toward external Telegram components.

## First calls (agents start here)

- `./bin/tgc next --json` — doctor triage as prioritized actions with exact commands.
- `./bin/tgc commands --json` — machine-readable registry of every command
  (purpose, level, safety, example). Same data as `tests/test_command_registry.py`
  enforces, so it cannot drift from `bin/`.

## Intent → command

| Intent | Command | Notes |
| --- | --- | --- |
| Что нового / прочитай чат за сегодня | `tg read today <chat> --limit 30 --json` | Live only; never mirror/archive. Fallback: MCP `telegram_read` `mode="fast"` |
| Keyword in dialog | MCP `telegram_search` | Then fetch context only for hits |
| Full today, nothing missed | MCP `telegram_read` `mode="full"` + page | Report `truncated` / `has_more_before` |
| Draft reply | MCP `telegram_prepare_reply` | No send without explicit user text |
| Send | MCP `telegram_confirmed_send` | Fresh `confirmation_token` from preview |
| Photos/video | MCP `telegram_inspect_media` / downloads | Never answer from captions only |
| Historical (allowlist) | `telegram-local-mirror` skill | Not for today/latest |
| Mirror status/read/search | `./bin/telegram-mirror-fast …` | Local exports only; promotion is maintenance |
| Control-plane health | `./bin/telegram-status`, `./bin/telegram-doctor --json` | Core profile, fails closed |
| Low-stakes today smoke | `./bin/telegram-fast-read-today me --limit 1` | Read-only fast path |
| Anything else | `./bin/tgc commands` | Pick by level/safety from the registry |

Forbidden until a read actually fails: mcporter, tool_search, plugin README,
doctor, launchd. `tg` on PATH: `./bin/telegram-kit --local`. For live Telegram
work read MCP resources first (`telegram://docs/routing`, `telegram://docs/tools`,
`telegram://docs/sources`); full skill: `$HOME/.agents/skills/telegram`. Do not
improvise Telethon calls or browse `telegram-mcp` unless debugging.

## Hard rules

- Do not move repos, refresh plugin cache, sync skill-index, rewrite LaunchAgents,
  start mirror jobs, or copy sessions from here without an explicit later plan.
- `generated/` may be rewritten by local doctor/status commands.
- Blocking doctor findings: stop and run `./bin/telegram-repair-plan --json`
  (dry-run) before proposing changes.
- Maintenance/release actions (`telegram-maintenance-doctor`,
  `telegram-release-gate`, `telegram-repair-plan-apply`, plugin cache
  materialization, adapter installs, docs sync) require an explicit
  maintenance/release task.

## Deep docs (read on demand)

- Doctor warn triage and command levels: `docs/agents/doctor-triage.md`
- Default MCP surface (16 tools) and release-gate naming: `docs/agents/mcp-surface.md`
- Telemetry locations and thresholds: `docs/agents/telemetry.md`
- Doc sync skill ↔ MCP resources: `docs/agents/doc-sync.md`
- Human map: `MAP.md`; roadmap: `TELEGRAM_AGENT_KIT_ROADMAP.md`
- Live MCP backend location: `policy/managed-systems.json` → `telegram-mcp`
- Portable plugin: `generated/telegram-plugin-package`

## Verification on this host

```bash
tg read today me --limit 1 --json   # payload.data_source == "live_telegram"
./bin/tgc next
./bin/telegram-doctor --json
```

Use `./bin/telegram-golden-read-smoke --json` only for release or live-smoke
verification (five dialogs from `policy/golden-dialogs.json`).
`TELEGRAM_GOLDEN_READ_SKIP=1` is CI/offline only.

## Agent skills

### Issue tracker

Issues and PRDs live as markdown under `.scratch/<feature-slug>/`. See `docs/agents/issue-tracker.md`.

### Triage labels

Five canonical triage roles (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`) map 1:1 to `Status:` lines in local issue files. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context layout: `CONTEXT.md` at the repo root and `docs/adr/` for decisions. See `docs/agents/domain.md`.
