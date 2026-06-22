# Telegram Control-Plane Rules

This directory is the local Telegram control-plane, not a Telegram runtime repo.
Default operation is direct full-surface local MCP for the owner's Telegram accounts.

## First calls

- Use the native MCP tools first. `telegram-main` is the main account on port
  `8799`; `telegram-pl` is the second account on port `8800`.
- Run `./bin/telegram-status` or `./bin/telegram-doctor --json` only when MCP
  calls fail or you are doing maintenance.
- `./bin/tgc commands --json` — machine-readable registry of every command
  (purpose, level, safety, example). Same data as `tests/test_command_registry.py`
  enforces, so it cannot drift from `bin/`.

## Intent → command

| Intent | Command | Notes |
| --- | --- | --- |
| Что нового / прочитай чат за сегодня | `tg read today <chat> --limit 30 --json` | Live only; never mirror/archive. Fallback: MCP `telegram_read` `mode="fast"` |
| Сколько постов / metadata count | `tg count posts <chat> --json` | Live metadata only; does not download history. Use `tg route '<task>' --json` when unsure |
| Keyword in dialog | MCP `telegram_search` | Then fetch context only for hits |
| Full today, nothing missed | MCP `telegram_read` `mode="full"` + page | Report `truncated` / `has_more_before` |
| Draft reply | MCP `telegram_prepare_reply` | No send without explicit user text |
| Send | MCP `telegram_send` or `send_message` | Direct one-call send on the selected local account |
| Edit/delete/forward/react/pin | MCP `edit_message`, `delete_messages`, `forward_messages`, `send_reaction`, `set_message_pinned` | Use exact chat/message ids |
| Photos/video | MCP `telegram_inspect_media` / downloads | Never answer from captions only |
| Historical (allowlist) | `telegram-local-mirror` skill | Not for today/latest |
| Mirror status/read/search | `./bin/telegram-mirror-fast …` | Local exports only; promotion is maintenance |
| Control-plane health | `./bin/telegram-status`, `./bin/telegram-doctor --json` | Core profile, fails closed |
| Low-stakes today smoke | `./bin/telegram-fast-read-today me --limit 1` | Read-only fast path |
| Anything else | `./bin/tgc commands` | Pick by level/safety from the registry |

Avoid `mcporter` and broad doctor checks on the hot path. `tg` on PATH:
`./bin/telegram-kit --local`. Do not improvise raw Telethon calls unless
debugging the MCP server itself.

## Hard rules

- Do not move repos, refresh plugin cache, sync skill-index, rewrite LaunchAgents,
  start mirror jobs, or copy sessions from here without an explicit later plan.
- `generated/` may be rewritten by local doctor/status commands.
- Blocking doctor findings mean the selected MCP account is not healthy. Fix
  the failing component directly; `telegram-repair-plan` is optional
  maintenance context, not a required preflight.
- Maintenance/release commands (`telegram-maintenance-doctor`,
  `telegram-release-gate`, plugin cache materialization, adapter installs,
  docs sync) are outside the normal agent hot path.

## Deep docs (read on demand)

- Doctor warn triage and command levels: `docs/agents/doctor-triage.md`
- Full MCP surface and release-gate naming: `docs/agents/mcp-surface.md`
- System map and verification order: `docs/agents/system-map.md`
- Telemetry locations and thresholds: `docs/agents/telemetry.md`
- Doc sync skill ↔ MCP resources: `docs/agents/doc-sync.md`
- Human map: `MAP.md`; roadmap: `TELEGRAM_AGENT_KIT_ROADMAP.md`
- Live MCP backend location: `policy/managed-systems.json` → `telegram-mcp`
- Portable plugin: `plugin`

## Verification on this host

```bash
tg read today me --limit 1 --json   # payload.data_source == "live_telegram"
./bin/tgc next
./bin/telegram-doctor --json
./bin/telegram-operator-status
```

Use `./bin/telegram-golden-read-smoke --json` only for release or live-smoke
verification (five dialogs from `policy/golden-dialogs.json`).
For a full post-change verification run, use
`./bin/telegram-regression-loop --include-live --json`; it keeps live smoke
sequential and avoids racing runtime tests.
`TELEGRAM_GOLDEN_READ_SKIP=1` is CI/offline only.

## Agent skills

### Issue tracker

Issues and PRDs live as markdown under `.scratch/<feature-slug>/`. See `docs/agents/issue-tracker.md`.

### Triage labels

Five canonical triage roles (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`) map 1:1 to `Status:` lines in local issue files. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context layout: `CONTEXT.md` at the repo root and `docs/adr/` for decisions. See `docs/agents/domain.md`.
