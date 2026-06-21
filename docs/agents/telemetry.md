# Local Telemetry

- Daily JSONL: `~/telegram-mcp/telemetry/daily/YYYY-MM-DD.jsonl` (30-day retention).
- Symlink: `~/telegram-mcp/telemetry.jsonl` → today’s file.
- Snapshot: `~/telegram-mcp/telemetry-stats.json` (runtime_stats + scheduler, ~60s; status warns when stale).
- Prometheus: `http://127.0.0.1:9109/metrics` (set `TELEGRAM_TELEMETRY_METRICS_PORT`; local profiles use `9109-9113`).
- Policy: `policy/telemetry/` (Prometheus scrape, alert rules, Grafana dashboard JSON).
- Summarize: `./bin/telegram-telemetry-status --json` or MCP `bin/telemetry-summary --json`.
- Summary includes top tool error buckets, top slow tools, cache totals, preflight counts, write-operation totals, and on-demand warnings for low cache hit rate, prewarm failures, FloodWait/rate limits, and stale stats.
- Insights: `./bin/telegram-insights --json` or `./bin/tgc insights --json` turns telemetry findings into prioritized improvement candidates.
- Event `source`: `mcp_tool`, `fast_read_cli`, `mcp_server` — only paths through MCP/fast-read are tracked.
- `doctor_check` includes `telemetry_summary` for the last 24h.
