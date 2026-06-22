# Telegram System Map

This is the short operational map for the local Telegram stack.

## Repos and Roles

- `/Users/sereja/Projects/tools/telegram` is the control-plane. It owns audits,
  policy, operator commands, feature status, generated plugin package, and docs.
- `/Users/sereja/Projects/families/telegram/telegram-digest/telegram-mcp` is the
  runtime. It owns Telethon sessions, MCP tools, live reads/writes, media,
  exports, telemetry emission, and launchd daemon code.
- `/Users/sereja/Projects/tools/telegram/plugin` is
  the portable plugin package generated from the control-plane.
- `/Users/sereja/Projects/runtime/telegram-mirror` is mirror runtime data. Treat
  it as recovery/historical context unless a task explicitly promotes mirror
  work.
- `/Users/sereja/Projects/.artifacts/telecrawl` is archive evidence. It is not
  live Telegram truth.

## Runtime Ports

- `8799`: main owner account, `crwddy` / `telegram-main`
- `8800`: legacy `telegram-pl`
- `8801`: `recklessou`
- `8802`: `teamsyncsage`
- `8803`: `vermassov`

## Source Routing

- Today/latest/recent/send/reply/media: live MCP or `tg`.
- Historical allowlisted mirror checks: `telegram-mirror-fast`.
- Archive search: telecrawl archive, with archive caveats.

## Main Operator Commands

- `./bin/telegram-operator-status`
- `./bin/telegram-maintenance-doctor --json --no-write-registry`
- `./bin/telegram-feature-status --json`
- `./bin/telegram-runtime-compat --json`
- `./bin/telegram-golden-read-smoke --json`
- `./bin/telegram-regression-loop --include-live --json`

## Verification Order

Use this order after meaningful changes:

1. Main control-plane tests.
2. Runtime MCP tests.
3. Restart MCP daemons.
4. Golden live-read smoke.
5. Maintenance doctor.
6. Feature status dry-run.

Do not run live smoke in parallel with runtime test suites.
