# 01 — Codex entry card and hot path

**Status:** ready-for-human

## Problem

Codex agents spend minutes on discovery (mcporter, README, doctor) before executing a live read.

## Done when

- Codex-specific entry visible at top of routing docs and skill preflight
- Forbidden preflight list matches AGENTS.md speed path
- `telegram-agent-docs-sync --check` passes

## Files

- `generated/telegram-plugin-package/skills/telegram/references/facade-routing.md`
- `generated/telegram-plugin-package/skills/telegram/SKILL.md`
- `AGENTS.md`
- `generated/telegram-plugin-package/README.md` (Codex onboarding blurb)