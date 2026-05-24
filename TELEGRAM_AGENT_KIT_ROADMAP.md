# Telegram Agent Kit Roadmap

This plan freezes the Oracle-backed direction for turning the local Telegram
tooling into a fast, safe, installable agent capability.

## Product Direction

Build a skill-first local Telegram agent kit, not an `@telegram`-first app.

The primary user path is natural language: after installation, a user asks their
agent to read, search, summarize, draft, send, inspect media, transcribe voice,
or export Telegram data. The agent routes through the installed Telegram skill
and local MCP runtime. Codex plugin support remains an adapter, not the core UX.

## Architecture

- `telegram-mcp`: local runtime that owns Telegram sessions, Telethon access,
  auth, rate limits, media/download roots, exports, and server-side policy.
- `telegram` skill: natural-language router and behavioral contract for agents.
- Host adapters: generated or materialized config for Codex, Claude Code,
  OpenCode, and standalone skill-aware agents.
- Installer/doctor: setup, host config generation, smoke checks, and drift gates.
- Control-plane: local audit/protection layer only; not the public runtime.

## Capability Model

- Default: read, search, context collection, draft/preview, scoped media
  inspection, and voice transcription.
- Write: send/reply only through server-side preview confirmation.
- Export: subscriber/member exports only with explicit PII acknowledgement and
  safe local output defaults.
- Admin: destructive/admin actions only through separate explicit escalation and
  plan/apply confirmation.

Do not expose raw full/admin tools as the normal installed surface. "All
functions available" means task workflows are available, not that every low-level
Telegram mutation tool is visible by default.

## Milestones

1. Fix default surface drift.
   - Plugin `.mcp.json`, approved facade policy, runtime facade, and installed
     cache must agree.
   - No unknown, write, destructive, or wildcard tools in default allowlists.

2. Make fast defaults real in server code.
   - Fast reads do not fetch pinned messages or voice transcriptions unless
     explicitly requested.
   - First-pass limits are small and agent-friendly.

3. Add server-side write confirmation.
   - Preview tools mint short-lived confirmation ids tied to account, target,
     reply id, exact text hash, parse mode, and expiry.
   - Send/reply tools refuse mutation without a valid unchanged confirmation.

4. Add task-shaped tools.
   - Prefer `telegram_read`, `telegram_search`, `telegram_prepare_reply`,
     `telegram_confirmed_send`, `telegram_inspect_media`, and
     `telegram_export_members` over raw Telegram/Telethon-shaped tools.

5. Build installer/adapters.
   - Generate or materialize host config for Codex, Claude Code, OpenCode, and
     standalone skill installs from one source of truth.
   - Fresh installs must not depend on `/Users/sereja` paths or private artifact
     roots.

6. Harden PII/media/session handling.
   - Export workflows require PII acknowledgement and private local defaults.
   - Media downloads are scoped, capped, local, and temporary by default.
   - Sessions, tokens, `.env`, media, exports, caches, and `__pycache__` are not
     packaged.

7. Release gates.
   - Surface, drift, packaging hygiene, fresh-install smoke, and prompt-injection
     tests must pass before publishing.

## Verification Gates

Run from the control-plane unless noted:

```bash
./bin/telegram-mcp-surface --json
./bin/telegram-plugin-drift --json
./bin/telegram-doctor --json
python3 -m pytest -q
```

Run from `telegram-mcp` for runtime changes:

```bash
./scripts/check.sh
./bin/contract-smoke --json
./bin/contract-smoke --profile app-media --json
python3 -m pytest -q
```

Release packaging must also verify:

```bash
grep -R "/Users/sereja\|\.session\|TELEGRAM_API_HASH\|TELEGRAM_SESSION_STRING" .
find . -name '__pycache__' -o -name '*.pyc' -o -name '.env' -o -name '*.session'
```

These grep/find commands are gates: expected release-package output is empty or
limited to explicitly documented migration examples.
