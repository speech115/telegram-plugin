# Local Telemetry

- Daily JSONL: `~/telegram-mcp/telemetry/daily/YYYY-MM-DD.jsonl` (30-day retention).
- Symlink: `~/telegram-mcp/telemetry.jsonl` → today’s file.
- Snapshot: `~/telegram-mcp/telemetry-stats.json` (runtime_stats + scheduler, ~60s).
- Prometheus: `http://127.0.0.1:9109/metrics` (set `TELEGRAM_TELEMETRY_METRICS_PORT`; use `9110` for PL profile).
- Policy: `policy/telemetry/` (Prometheus scrape, alert rules, Grafana dashboard JSON).
- Summarize: `./bin/telegram-telemetry-status --json` or MCP `bin/telemetry-summary --json`.
- Event `source`: `mcp_tool`, `fast_read_cli`, `mcp_server` — only paths through MCP/fast-read are tracked.
- `doctor_check` includes `telemetry_summary` for the last 24h.
