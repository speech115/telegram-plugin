# telegram-mcp

Telegram MCP server for Claude Code and other MCP clients. The repo contains the
runtime, typed Telegram tools, health/doctor diagnostics, and small ops scripts
for a local launchd-managed HTTP daemon.

## Runtime model

- Default transport for daemon mode: `streamable-http`
- Default bind: `127.0.0.1:8799`
- Default MCP HTTP path: `/mcp`
- Default response mode for HTTP requests: JSON
- Session backend: `TELEGRAM_SESSION_STRING` or file session in `~/.telegram-mcp/`

`stdio` is still supported for direct local execution, but the project defaults
to a shared-client HTTP path to avoid repeated session lock contention.

## Setup

1. Create `.env` with `TELEGRAM_API_ID` and `TELEGRAM_API_HASH`.
2. Optionally set `TELEGRAM_SESSION_STRING` to avoid SQLite session files.
3. Install the package into the local virtualenv:

```bash
uv pip install -e .
```

## Agent docs (MCP resources)

Routing and safety docs are exposed as markdown MCP resources so agents can fetch
small slices instead of loading the full Telegram skill:

- `telegram://docs/index` — catalog
- `telegram://docs/routing` — fast defaults and tool choice (read first)
- `telegram://docs/tools` — default facade surface
- `telegram://docs/sources` — live vs mirror vs archive
- `telegram://docs/writes` — send/preview hard stops
- `telegram://docs/media` — media and voice rules
- `telegram://me` — current account JSON

Canonical manifest: `skills/telegram/agent-docs/manifest.json` in the plugin package.
Generated MCP files live in `docs/agent/`. Run `bin/sync-agent-docs` after editing
`references/` or the manifest. Restart the HTTP daemon after sync.

## Useful commands

```bash
PYTHONPATH=src .venv/bin/python -m telegram_mcp
TELEGRAM_MCP_TRANSPORT=stdio PYTHONPATH=src .venv/bin/python -m telegram_mcp health
TELEGRAM_MCP_TRANSPORT=stdio PYTHONPATH=src .venv/bin/python -m telegram_mcp doctor
mcporter call telegram.get_me --timeout 30000 --output json
mcporter list telegram --json
./bin/doctor --json
./bin/status --json
./bin/contract-smoke --json
./bin/contract-smoke --profile app-media --json
./bin/contract-smoke --check-cache-stats --json
./bin/stress-readonly --iterations 24 --concurrency 4 --json
./bin/stress-readonly --mode cache-pair --iterations 12 --json
./bin/check-plugin-drift --json
./bin/install-adapters --host all --json
./scripts/check.sh
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p 'test_*.py'
PYTHONPATH=src .venv/bin/python -m compileall src tests
```

`./bin/install-adapters` is safe by default: it prints a dry-run plan for Codex,
Claude Code, OpenCode, and standalone skill adapter snippets. Use `--apply` only
with an explicit `--output-dir`; it writes snippets there and does not mutate live
host config files.

## Dialog facade

For common live Telegram work the repo now exposes a high-level dialog facade on
top of the existing rich tool surface:

- `resolve_dialog`
- `read_dialog_by_date`
- `read_recent_dialog`
- `search_dialog_messages`
- `send_dialog_message`
- `reply_in_dialog`

These tools keep the raw Telegram MCP API intact, but give agents one stable
front door for normal read/send/reply tasks. The facade resolves reusable
`dialog_ref` handles, routes live reads through one shared internal read engine,
and does not silently fall back to `telegram-mirror`.

Use the facade for ordinary conversational Telegram work. Use the existing rich
tool set for power-user operations such as contacts, stories, groups, media,
moderation, and lower-level automation.

Voice notes in the dialog facade are transcribed through Telegram's built-in
`TranscribeAudioRequest` path by default, with a small default budget so one
large read cannot spend unbounded time in Telegram transcription. Raise
`max_voice_transcriptions` explicitly when a run needs more voice notes. Do not
download Telegram voice notes for local Whisper/CPU transcription; pass
`include_voice_transcription=false` only when the caller explicitly wants
metadata without transcript text.
For fast scans, pass `include_sender_name=false`; message `sender_id` is still
returned, but the read path skips extra `get_sender()` calls.

Examples:

```bash
mcporter call telegram.read_dialog_by_date --args '{"chat":"@targetdaddy","date_from":"2026-04-17","date_to":"2026-04-17","page_size":50}'
mcporter call telegram.reply_in_dialog --args '{"chat":"@targetdaddy","message_id":123,"text":"Принял, посмотрю"}'
mcporter call telegram.download_media_batch --args '{"chat":"@targetdaddy","message_ids":[123,124],"concurrency":2}'
```

## Task facade v2

The next facade layer is for task-shaped routing, not a new Telegram backend.
Agents should use it when the user asks for ordinary live-dialog tasks such as:

- read today's dialog
- collect enough dialog context for a decision
- prepare a reply draft

The intended v2 tool names are:

- `read_today_dialog`
- `collect_dialog_context`
- `prepare_dialog_reply`

This layer should compose the dialog facade slice above. It must not auto-send,
schedule, or run an autopilot loop. All writes stay explicit through the existing
write tools, currently `send_dialog_message` and `reply_in_dialog`.

`telegram-mirror` remains outside this live task path. Use mirror data only for
archive, indexing, historical analysis, or explicit mirror requests. Do not
silently mix mirror results into live task facade reads.

## Fast read and media path

Dialog reads and dialog-scoped searches use a short, separate result cache
controlled by `TELEGRAM_DIALOG_READ_CACHE_TTL_SECONDS` (default `5`). This cache
is intentionally shorter than the general read-only cache so repeated agent
turns can reuse the same live window without making normal Telegram state feel
stale. Message-changing writes invalidate dialog read/search cache prefixes.

`download_media_batch` deduplicates repeated message ids for the actual Telegram
download work, preserves the requested item order in the public result, and
clamps local batch concurrency to `TELEGRAM_SCHEDULER_MEDIA_CONCURRENCY`.

`doctor_check` exposes runtime counters for the fast path:

- `dialog_read_cache_hit` / `dialog_read_cache_miss`
- `dialog_search_cache_hit` / `dialog_search_cache_miss`
- `dialog_read_cache_hit_rate`
- `dialog_search_cache_hit_rate`
- `cache_invalidated_after_write`
- `download_media_batch_dedupe_count`
- `download_media_batch_effective_concurrency`

These counters are also visible through `./bin/status --json` in daemon mode.

## App-style and media helpers

The app-style surface is intentionally just aliases over the dialog facade:

- `find_dialog` -> `resolve_dialog`
- `read_dialog` -> `read_today_dialog` when `day` is set, otherwise `read_recent_dialog`
- `collect_context` -> `collect_dialog_context`
- `draft_reply` -> `prepare_dialog_reply`
- `reply_message` -> `reply_in_dialog`

The existing rich tools remain intact. `send_message` still uses the low-level
message path; `send_dialog_message` remains the facade send path.

Preview-only write helpers are available for agent safety:

- `prepare_send_message`
- `prepare_reply_message`

They resolve/validate the target and return `send_tool` plus
`send_args_preview`, but never call the write path.

For media-heavy dialog work, use `prepare_media_inspection_manifest` first. It
returns media metadata and any already-known local download path without
downloading files. The manifest uses media metadata already present in the read
path and only falls back to an extra Telegram message fetch when the read payload
does not include enough media type data. Use `download_dialog_media` only after
selecting explicit message ids; it delegates to `download_media_batch`.

## Planning docs

- repo roadmap: `docs/superpowers/roadmaps/2026-04-17-telegram-mcp-roadmap.md`
- facade design: `docs/superpowers/specs/2026-04-17-telegram-app-facade-design.md`
- facade implementation plan: `docs/superpowers/plans/2026-04-17-telegram-dialog-facade-implementation.md`

## Ops scripts

- `scripts/install-launchd.sh` installs the local HTTP daemon on `127.0.0.1:8799`
- `scripts/install-launchd.sh` now waits for a successful local `health` probe
  before reporting success, so reinstall no longer returns early while the daemon
  is still half-awake
- `scripts/status.sh` prints `launchctl`, `health`, `doctor`, recent logs, and the
  explicit exit code of each diagnostic command without failing the whole status view
- `scripts/smoke-check.sh` runs a strict local health/doctor/smoke flow and exits
  immediately with a clear error message when `health`, `doctor`, or the listener
  probe fails
- `scripts/check.sh` is the canonical local verification path: unit tests,
  `compileall`, then `smoke-check`
- `bin/contract-smoke` runs a live external MCP contract check through
  `mcporter`: tool listing, repeated `collect_dialog_context`,
  `prepare_dialog_reply`, and `search_dialog_messages` shape checks
- `bin/contract-smoke --profile app-media` checks the app-style read aliases,
  preview-only write helpers, and media manifest shape without sending messages
  or requiring the selected dialog to contain media
- `bin/contract-smoke --check-cache-stats` proves cache reuse by checking
  `doctor.runtime_stats` hit counters instead of relying on process-level
  latency
- `bin/stress-readonly` runs bounded daemon pressure checks through `mcporter`
  using only safe read-only calls (`get_me`, `resolve_dialog`,
  `collect_dialog_context`, `read_today_dialog`, `search_dialog_messages`);
  `--mode cache-pair` repeats identical facade reads in pairs so cache-hit
  effects are visible in latency diagnostics
- Local telemetry uses daily JSONL files under `~/telegram-mcp/telemetry/daily/`
  (30-day retention) plus symlink `~/telegram-mcp/telemetry.jsonl` → today.
  Periodic `~/telegram-mcp/telemetry-stats.json` snapshots and Prometheus text
  metrics at `http://127.0.0.1:9109/metrics` (`TELEGRAM_TELEMETRY_METRICS_PORT`;
  use `9110` for the second HTTP profile). Events include `source` labels
  (`mcp_tool`, `fast_read_cli`, …) so operators can see which path was used.
  Summarize with `bin/telemetry-summary --json`; import Grafana dashboard from
  control-plane `policy/telemetry/grafana-dashboard.json`.
- `bin/check-plugin-drift` maps the local Telegram skill/plugin layers:
  live standalone skill, source plugin bundle, staged marketplace copy, managed
  plugin cache, and plugin `.mcp.json` files. It is read-only and reports
  `canonical_source` plus `sync_safe`; only treat source sync as safe when all
  known skill layers match. The managed cache path is resolved from the source
  plugin manifest version, so a source bump such as `0.1.1` is checked against
  the matching cache version. If it reports `unproven`, use the live skill as
  the current agent-routing layer and prove the installer flow before touching
  managed cache files.
- The Codex plugin apply path for the local Telegram plugin is
  source-first: update `/Users/sereja/Projects/tools/telegram/plugin`, bump its plugin
  manifest version, re-add the local marketplace if Codex still points at a stale
  staged root, and materialize only the new versioned cache from that canonical
  source. Leave older cache versions intact. Do not run any apply path while
  `bin/check-plugin-drift --json` reports `installer_flow.safe_to_apply=false`;
  that would just package the wrong source into installed layers.
- in daemon mode `scripts/smoke-check.sh` also does one facade-level probe
  through `mcporter` (`resolve_dialog -> collect_dialog_context`) so the external
  client path catches stale or missing facade wiring
- in `streamable-http` mode the ops scripts probe the daemon through `mcporter`,
  which matches the normal external-client path instead of opening a second direct
  Python client against the shared Telegram session
- both scripts now detect a missing repo-local `.venv/bin/python` and print an
  explicit bootstrap hint instead of surfacing a raw shell `127`
- daemon-mode scripts also detect a missing `mcporter` binary and explain the fix

The `health` and `doctor` CLI commands include the effective runtime transport
and resolved `endpoint_url`, so it is easy to confirm the actual bind after env
overrides or launchd changes.
`doctor` also reports the Telethon scheduler lanes, limits, queue depth, and
last timeout/rate-limit state for the shared daemon.
They keep JSON on stdout, but now return a non-zero exit code when the health
report is unhealthy or the doctor status is not `ok`, so shell smoke checks can
fail fast without losing the structured payload.

## Environment

See [.env.example](.env.example) for the expected variables. The most relevant
daemon variables are:

- `TELEGRAM_MCP_TRANSPORT=streamable-http`
- `TELEGRAM_MCP_HOST=127.0.0.1`
- `TELEGRAM_MCP_PORT=8799`
- `TELEGRAM_MCP_HTTP_PATH=/mcp`
- `TELEGRAM_MCP_JSON_RESPONSE=true`
- `TELEGRAM_MCP_INCLUDE_DIAGNOSTICS=false`
- `TELEGRAM_TELEMETRY_ENABLED=true`
- `TELEGRAM_TELEMETRY_LOG_PATH=<home>/telegram-mcp/telemetry.jsonl`
- `TELEGRAM_TELEMETRY_STATS_PATH=<home>/telegram-mcp/telemetry-stats.json`
- `TELEGRAM_TELEMETRY_STATS_FLUSH_SECONDS=60`
- `TELEGRAM_MCP_PROBE_TIMEOUT_SECONDS=15`
- `TELEGRAM_DOWNLOAD_REGISTRY_PATH=<download-dir>/download_registry.sqlite3`
- `TELEGRAM_DOWNLOAD_RETENTION_DAYS=0`
- `TELEGRAM_DOWNLOAD_CLEANUP_INTERVAL_SECONDS=3600`
- `TELEGRAM_CACHE_TTL=60`
- `TELEGRAM_DIALOG_READ_CACHE_TTL_SECONDS=5`
- `TELEGRAM_RESULT_CACHE_SIZE=256`
- `TELEGRAM_READ_INFLIGHT_DEDUPE_SIZE=128`
- `TELEGRAM_TRANSCRIPT_CACHE_SIZE=256`
- `TELEGRAM_CONNECT_TIMEOUT_SECONDS=15`
- `TELEGRAM_TOOL_READ_TIMEOUT_SECONDS=30`
- `TELEGRAM_TOOL_WRITE_TIMEOUT_SECONDS=30`
- `TELEGRAM_TOOL_MEDIA_TIMEOUT_SECONDS=120`
- `TELEGRAM_TOOL_TRANSCRIBE_TIMEOUT_SECONDS=45`
- `TELEGRAM_TOOL_ENRICH_TIMEOUT_SECONDS=15`
- `TELEGRAM_SCHEDULER_READ_CONCURRENCY=4`
- `TELEGRAM_SCHEDULER_WRITE_CONCURRENCY=1`
- `TELEGRAM_SCHEDULER_MEDIA_CONCURRENCY=2`
- `TELEGRAM_SCHEDULER_TRANSCRIBE_CONCURRENCY=1`
- `TELEGRAM_SCHEDULER_ENRICH_CONCURRENCY=4`
- `TELEGRAM_CIRCUIT_BREAKER_ENABLED=true`
- `TELEGRAM_CIRCUIT_BREAKER_FAILURE_THRESHOLD=3`
- `TELEGRAM_CIRCUIT_BREAKER_RECOVERY_SECONDS=30`
- `TELEGRAM_DEFAULT_VOICE_TRANSCRIPTION_BUDGET=3`
- `TELEGRAM_READ_MAX_MESSAGES=100`
- `TELEGRAM_READ_MAX_CHARS=40000`
- `TELEGRAM_READ_MAX_MEDIA_ITEMS=25`
- `TELEGRAM_WRITE_AUDIT_ENABLED=true`
- `TELEGRAM_WRITE_AUDIT_LOG_PATH=<home>/telegram-mcp/write-audit.jsonl`

Message read outputs include `truncated=true` and `truncated_reason` when these
hard caps cut the returned payload.
Write calls append metadata-only JSONL audit events by default; message text,
captions, file paths, and raw error text are not logged.

## Notes

- Never commit `.env` or Telegram session artifacts.
- Downloaded Telegram media is stored under `TELEGRAM_DOWNLOAD_DIR`. Cleanup is
  disabled by default; run `bin/cleanup-downloads --dry-run --json` to inspect
  candidates and `bin/cleanup-downloads --delete --json` to delete explicitly.
- `TELEGRAM_DOWNLOAD_REGISTRY_PATH` stores local metadata for downloaded media.
  `TELEGRAM_TRANSCRIPT_CACHE_SIZE` controls a cache that stores only completed
  transcriptions by chat/message.
- If HTTP config changes, update runtime defaults, launchd install script, and
  smoke/status docs together.
