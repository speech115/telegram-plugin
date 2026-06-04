# Agent-fast Telegram kit — design brief

**Status:** approved (grill-me, 2026-06-04)  
**Primary host:** Codex (incident: agent spent long time discovering how to read a chat)

## North star

Any agent on this machine answers «что нового в чате X» from **live Telegram** in ≤2 tool calls (or one CLI), without archive substitution and without infrastructure spelunking first.

## Decisions (locked)

| Topic | Choice |
| --- | --- |
| Audience | Any local agent (B); portable kit as release gate (C) |
| Speed | All metrics + SLO; tighten after 1 week telemetry |
| Stability | Correct source (B) + fail-closed (C) |
| Scope | `telegram-mcp` + skill/plugin + control-plane |
| MCP surface | 16 task-shaped tools default; fast CLI first |
| Read default | Fast; full only on request |
| Runtime | One daemon; aggressive prewarm + session reuse |
| Quality gates | pytest/smoke + 5–10 golden dialogs (manual) |
| Cache | B for «что нового»; A only for «перескажи то же» |
| Sacred | `telegram_read` … `telegram_export_members`, resolve/find; downloads capped; `doctor_check` not hot path |

## SLO (week 1 baseline)

| Metric | Target |
| --- | --- |
| Fast read p95 (limit≤30) | ≤ 3 s |
| Cold first tool after idle | ≤ 8 s |
| Typical «что нового» | ≤ 2 tool calls, ≤ 60 s wall |
| Live vs archive mix-up | 0 (fail-closed) |
| Cache hit (repeat read ≤10 min, same worker) | ≥ 70% |

## Root cause (Codex incident)

Routing/discovery failure (branch 4 holes #1 + #4): rules existed in skill but were buried; agent explored mcporter/README/doctor before `tg read today`.

## Execution phases

### P0 — Agent does not wander (current)

- Codex entry card (8-line hot path + forbidden preflight)
- Skill + `telegram://docs/routing` + AGENTS.md alignment
- `tg` on PATH warn in doctor
- Adapter snippets under `generated/adapters/codex/`
- Telemetry: `preflight_violation` / `seconds_to_first_read` (telegram-mcp, follow-up issue)

### P1 — Read is fast (runtime)

- Fast server defaults; prewarm; session stickiness; read cache TTL (Q9 B)

### P2 — Stability

- Surface parity CI; routing tests; fail-closed error copy

### P3 — Portable + SLO tighten

- No `/Users/sereja` in generated registry; Grafana SLO dashboard

## Verification

```bash
./bin/telegram-fast-read-today me --limit 1
./bin/telegram-agent-docs-sync --check --no-restart
./bin/telegram-mcp-surface --json
python3 -m pytest tests/test_control_plane.py -q -k "fast_read or agent_docs"
```

Codex synthetic: «прочитай @X за сегодня» → 0 preflight violations; first payload ≤ 8 s cold.