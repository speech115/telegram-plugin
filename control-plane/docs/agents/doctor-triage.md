# Doctor Warn Triage

Use doctor for control-plane health, not for ordinary live reads. Interpret
`./bin/telegram-doctor --json` by severity, not by the top-level word alone.
`telegram-doctor` is the fast core profile by default; use
`./bin/telegram-maintenance-doctor --json` or
`./bin/telegram-doctor --profile maintenance --json` only for broad
release/archive/recovery checks:

1. `status=ok`: control-plane checks are clean.
2. `status=warn` with `summary.blocking_findings=0`: operational warning, not a
   release blocker. Read `findings[].component` before acting.
3. `status=fail` or any blocking finding: stop and use
   `./bin/telegram-repair-plan --json` before proposing changes.

`./bin/tgc next --json` automates this triage: it maps each finding component
to the exact drill-down command and appends the repair-plan step when blocking
findings are present.

## Common non-blocking maintenance warnings

- `mcp_telemetry`: recent MCP tool errors or high error rate. Check
  `./bin/telegram-telemetry-status --json`; do not rewrite runtime routing from
  this signal alone.
- `telecrawl_known_gaps`: archive import backlog or terminal archive gaps.
  Telecrawl is archive evidence, not live/current Telegram truth.
- `plugin_cache_needs_materialization`: plugin/cache install lag. This is
  distinct from default MCP surface health.

Surface health and maintenance health are separate layers: a green
`telegram-mcp-surface --json` can coexist with maintenance `warn`, and plugin
drift can be green while another runtime layer warns.

## Operator command levels

- Daily health: `./bin/telegram-status` for a human summary, or
  `./bin/telegram-doctor --json` for machine-readable core output.
- Mirror fast path: use `./bin/telegram-mirror-fast status/read/search` first
  when the task explicitly asks for mirror; it reads local export/ledger files
  only. Mirror promotion/preflight is maintenance, not daily mirror use.
- Drill-down: run `telegram-mcp-surface`, `telegram-docs-audit`,
  `telegram-telemetry-status`, `telegram-telecrawl-status`, or other component
  checks only after doctor points at that component.
- Maintenance/release: `telegram-maintenance-doctor`, `telegram-release-gate`,
  plugin cache materialization, adapter installs, and docs sync require an
  explicit maintenance/release task.
