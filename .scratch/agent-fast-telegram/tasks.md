# Tasks: agent-fast-telegram

## P0 — Routing (done 2026-06-04)

- [x] Save brief + issues 01–02
- [x] Codex entry card: skill, facade-routing, AGENTS.md, plugin README
- [x] `generated/adapters/codex/` (`telegram-codex-entry.md`, routing note, mcp.json)
- [x] Doctor: `tg_on_path` warn in `audit_fast_read_adapter`
- [x] `telegram-agent-docs-sync` + pytest (fast_read, agent_docs)
- [x] Codex plugin cache refresh on host (`codex plugin remove/add`, 2026-06-04)

## P0.4 — Telemetry (done 2026-06-04)

- [x] `preflight_violation` + `seconds_to_first_read` events
- [x] `agent_preflight` block in telemetry summarize
- [x] Doctor warn `telemetry_preflight_violations` (>10 / 24h)

## P1 — Runtime speed (partial)

- [x] Fast defaults already in `telegram_read` (verified)
- [x] Prewarm: HTTP `get_me` + `telegram_read me`; shared wrapper startup prewarm
- [x] `mcp_shared_client` default true
- [x] HTTP worker stickiness documented (facade-routing: limit + use tg CLI mitigation)
- [x] `bin/tg` symlink-safe wrapper; kit_install links `~/bin/tg` → kit wrapper
- [x] Read cache TTL stays 5s (Q9 B: live on repeat «что нового»)

## P2 — Stability (done 2026-06-04)

- [x] CI gates: `mcp-surface` + `source-routing-audit` in release-gates ci mode
- [x] Source-routing tests + audit samples (today → live_mcp, archive blocked)
- [x] Fail-closed `format_contract_error` with `| next:` action (telegram-mcp)
- [x] HTTP session notes in facade-routing (shared client + stateless caveat)

## P3 — Portable + observability (partial)

- [x] Registry home path → `<home>` + scan pattern + fast_read_adapter projection
- [x] Grafana panels: preflight violations, seconds_to_first_read
- [x] Prometheus events for preflight / first-read
- [x] `policy/telemetry/slo-targets.json` (week-1 baseline; operator tightens alert-thresholds)
- [ ] Week-2 SLO tighten from telemetry (operator)
- [x] Local release gate green: write-safety-smoke PYTHONPATH, plugin-drift ignores `.DS_Store`

## Golden dialogs (2026-06-04)

- [x] Saved Messages: `me` (@CrwDdy)
- [x] Channel: `-1003850136767` → **Конспекты**
- [x] 1:1: `@commercialclub`, `@AndrewBTO`, `@brexit_man` (see `golden-dialogs.md`)
- [x] Group — не нужен (достаточно 5 диалогов)
- [x] `policy/golden-dialogs.json` + `bin/telegram-golden-read-smoke`
- [x] Release gate `tg-read-smoke` (local only); doctor probe `saved-messages`