# Telegram Control-Plane Plan

This repo is the canonical operator entrypoint for local Telegram tooling.

## Goal

Make Telegram tooling understandable and hard to delete accidentally without
turning this directory into a monorepo or private-state dump.

## Execution Order

1. Keep `/Users/sereja/Projects/tools/telegram` as the control-plane and
   protection layer.
2. Keep live/runtime systems in their own homes:
   - live Telegram MCP backend in `telegram-mcp`;
   - mirror recovery/runtime candidate in `telegram-mirror`;
   - telecrawl archives and account state outside this repo;
   - plugin and skills in their normal Codex locations.
3. Register every Telegram-related system in `policy/managed-systems.json`.
4. Make `telegram-doctor` fail closed when a blocking-protected system is
   missing, has the wrong path kind, or lacks required marker files.
5. Use `MAP.md` as the human-readable index and `PROTECTION.md` as the cleanup
   contract.
6. Register this repo in `karpathy-kb` so future agents do not treat it as
   scratch or unmanaged drift.

## Non-Goals

- Do not move repos into this tree.
- Do not copy sessions, Telegram Desktop `tdata`, archive DBs, media payloads,
  subscriber exports, or secrets into this repo.
- Do not start mirror watchers/backfills/sync jobs from this milestone.
- Do not rewrite LaunchAgents or refresh plugin cache without a later explicit
  dry-run repair plan.

## Milestone Status

Roadmap milestones 1–7 are implemented in code and gates:

- default surface parity, fast reads, confirmed send, task-shaped tools;
- portable `install-adapters` / `check-release-gates` in `telegram-mcp`;
- private-cache media defaults and PII-gated `telegram_export_members`;
- control-plane `telegram-release-gate` runs packaging, adapter, and safety gates.

## Verification

For day-to-day health, use:

```bash
./bin/telegram-status
./bin/telegram-doctor --json
./bin/telegram-mirror-fast status --json
```

Expected current shape:

- `telegram-doctor`: fast core profile only
- core covers live Telegram routing/surface safety, fast read, minimal live
  runtime state, and lightweight mirror status
- mirror fast path reads existing local exports with
  `telegram-mirror-fast read/search`; it does not start watchers or backfills
- release/archive/telemetry/plugin/mirror-promotion checks are not core

For release/maintenance work, run `./bin/telegram-maintenance-doctor --json` or
`./bin/telegram-release-gate`. Use component audits such as
`telegram-mcp-surface`, `telegram-docs-audit`, or `telegram-telemetry-status`
only as drill-down from doctor findings.

## karpathy-kb

Canonical entity: `research/karpathy-kb/wiki/entities/telegram-control-plane.md`
