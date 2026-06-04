# 02 — Telemetry: preflight violations

**Status:** ready-for-human

## Problem

Cannot measure Codex «minutes before first read» without events.

## Done when

`telegram-mcp` emits JSONL events:

- `preflight_violation` (tool/name before first successful read)
- `seconds_to_first_read` on session or turn

Control-plane `telegram-telemetry-status` surfaces counts in summary.

## Repo

`families/telegram/telegram-digest/telegram-mcp` (runtime)