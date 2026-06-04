# 04 — P3 portable registry + telemetry dashboards

**Status:** ready-for-human

## Shipped

- `registry_redaction`: normalize `/Users/<user>/` → `<home>/` in persisted paths
- `registry-schema`: `agent_preflight` on mcp_telemetry, safer fast_read_adapter fields
- Grafana: preflight + first-read panels
- Prometheus: `preflight_violation`, `seconds_to_first_read` events

## Operator

- `./bin/telegram-doctor --json` refreshes `generated/observed-registry.json`
- Restart MCP HTTP after runtime changes for prewarm/preflight hooks