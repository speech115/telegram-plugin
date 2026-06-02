# Telegram Control-Plane Rules

- This directory is the local Telegram control-plane, not a Telegram runtime repo.
- Default operation is read-only toward external Telegram components.
- Do not move repos, refresh plugin cache, sync skill-index, rewrite LaunchAgents,
  start mirror jobs, or copy sessions from here without an explicit later plan.
- `generated/` may be rewritten by local doctor/status commands.
- The first milestone is allowed to fail closed on known defects.

## Agent Entry (read this first)

For live Telegram work, read MCP resources first (smaller than the full skill):

- `telegram://docs/routing`, `telegram://docs/tools`, `telegram://docs/sources`

Full skill: `$HOME/.agents/skills/telegram` (symlink to
`generated/telegram-plugin-package/skills/telegram`). Do not improvise Telethon
calls or browse `telegram-mcp` unless debugging.

### Speed path (low-stakes "что нового / за сегодня")

1. Classify: current/today/recent → **live only** (never mirror/archive).
2. On this host, run first:
   `bin/telegram-fast-read-today <chat> --limit 30` (read-only, ~sub-second).
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

### Default MCP surface (21 tools)

Only these are exposed to agents via plugin allowlist: `telegram_read`,
`telegram_search`, `telegram_prepare_reply`, `telegram_confirmed_send`,
`telegram_inspect_media`, `telegram_export_members`, `resolve_dialog`,
`find_dialog`, `collect_dialog_context`, `collect_context`, prepare/download
helpers, `get_me`, `doctor_check`. Raw `send_dialog_message` / `reply_in_dialog`
are **not** on the default surface.

### Doc sync (skill ↔ MCP resources)

Edit `generated/telegram-plugin-package/skills/telegram/references/`, then:

```bash
./bin/telegram-agent-docs-sync
```

Restarts local MCP HTTP daemons automatically after sync. CI uses `--check --no-restart`.
`build-plugin-package` runs the same sync automatically. Manifest:
`skills/telegram/agent-docs/manifest.json`.

### Telemetry (local)

- JSONL: `~/telegram-mcp/telemetry.jsonl` (tool latency, cache, errors; no message text).
- Snapshot: `~/telegram-mcp/telemetry-stats.json` (runtime_stats + scheduler, ~60s).
- Summarize: `./bin/telegram-telemetry-status --json` or MCP `bin/telemetry-summary --json`.
- `doctor_check` includes `telemetry_summary` for the last 24h.

### Verification on this host

```bash
./bin/telegram-fast-read-today me --limit 1
./bin/telegram-mcp-surface --json
./bin/telegram-doctor --json
./bin/telegram-telemetry-status --json
```

Fast read must return `payload.data_source == "live_telegram"`, not
`Unknown tool`.

### Runtime locations

- Live MCP backend: `policy/managed-systems.json` → `telegram-mcp`
- Portable plugin: `generated/telegram-plugin-package`
- Human map: `MAP.md`, roadmap: `TELEGRAM_AGENT_KIT_ROADMAP.md`