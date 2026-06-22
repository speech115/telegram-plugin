from __future__ import annotations

from typing import Any


READ_TOOLS = {
    "telegram_read",
    "telegram_search",
    "tg_read_today",
    "tg_read_recent",
    "tg_search",
}

DEFAULT_IGNORED_TOOL_ERROR_TOOLS = {
    "broken_tool",
    "forbidden_tool",
    "invalid_range_tool",
    "invalid_username_tool",
    "ok_tool",
    "peer_flood_tool",
    "rate_limited_tool",
    "slow_tool",
}


def top_slow_tools(tool_latency: dict[str, Any], *, limit: int = 10) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for tool, stats in tool_latency.items():
        if not isinstance(stats, dict):
            continue
        p95 = stats.get("p95_ms")
        max_ms = stats.get("max_ms")
        if not isinstance(p95, int | float) and not isinstance(max_ms, int | float):
            continue
        rows.append(
            {
                "tool": str(tool),
                "count": stats.get("count"),
                "p95_ms": p95,
                "max_ms": max_ms,
            }
        )
    return sorted(
        rows,
        key=lambda item: (
            -(float(item["p95_ms"]) if isinstance(item.get("p95_ms"), int | float) else -1.0),
            -(float(item["max_ms"]) if isinstance(item.get("max_ms"), int | float) else -1.0),
            item["tool"],
        ),
    )[:limit]


def evaluate_mcp_telemetry(
    summary: dict[str, Any],
    *,
    thresholds: dict[str, Any],
    effective_window: float,
    stats_file_age_seconds: float | None,
    stats_lanes: dict[str, Any],
    metrics_targets: list[dict[str, Any]],
) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    summary_status = summary.get("status")
    events_in_window = int(summary.get("events_in_window") or 0)
    raw_tool_errors = int(summary.get("tool_errors") or 0)
    min_events = int(thresholds.get("min_events_for_rate_checks", 20))
    max_tool_errors = int(thresholds.get("max_tool_errors", 10))
    max_error_rate = float(thresholds.get("max_tool_error_rate", 0.25))
    max_read_p95 = float(thresholds.get("max_telegram_read_p95_ms", 5000))
    min_cache_hit_rate = thresholds.get("min_cache_hit_rate_when_cache_tracked")
    max_prewarm_failure_rate = thresholds.get("max_prewarm_failure_rate")
    max_read_floodwait_events = thresholds.get("max_read_floodwait_events")
    max_lane_rate_limited = thresholds.get("max_lane_rate_limited")
    ignored_tool_error_tools = set(DEFAULT_IGNORED_TOOL_ERROR_TOOLS)
    ignored_tool_error_tools.update(
        str(tool)
        for tool in thresholds.get("ignored_tool_error_tools", [])
        if isinstance(tool, str) and tool
    )
    raw_tool_error_buckets = summary.get("tool_error_buckets") if isinstance(summary.get("tool_error_buckets"), list) else []
    tool_error_buckets: list[dict[str, Any]] = []
    ignored_tool_errors = 0
    for bucket in raw_tool_error_buckets:
        if not isinstance(bucket, dict):
            continue
        count = int(bucket.get("count")) if isinstance(bucket.get("count"), int | float) else 1
        if str(bucket.get("tool")) in ignored_tool_error_tools:
            ignored_tool_errors += count
            continue
        tool_error_buckets.append(bucket)
    tool_errors = max(0, raw_tool_errors - ignored_tool_errors) if raw_tool_error_buckets else raw_tool_errors

    if summary_status == "missing":
        findings.append(
            {
                "id": "telemetry_log_missing",
                "severity": "warn",
                "message": (
                    "MCP telemetry logs are not present yet. Restart HTTP MCP with "
                    "TELEGRAM_TELEMETRY_ENABLED=true (default) to begin collecting events."
                ),
            }
        )
    elif summary_status == "ok" and events_in_window == 0:
        findings.append(
            {
                "id": "telemetry_no_recent_events",
                "severity": "warn",
                "message": (
                    f"No telemetry events in the last {effective_window:g}h. "
                    "Confirm MCP HTTP daemons are running and receiving tool traffic."
                ),
            }
        )
    elif tool_errors >= max_tool_errors:
        findings.append(
            {
                "id": "telemetry_high_tool_error_count",
                "severity": "warn",
                "message": f"MCP telemetry recorded {tool_errors} tool errors in the recent window.",
            }
        )

    event_counts = summary.get("event_counts")
    tool_calls = int(event_counts.get("tool_call", 0)) if isinstance(event_counts, dict) else 0
    if tool_calls >= min_events and tool_errors / tool_calls > max_error_rate:
        findings.append(
            {
                "id": "telemetry_high_tool_error_rate",
                "severity": "warn",
                "message": (
                    f"Tool error rate {tool_errors}/{tool_calls} exceeds "
                    f"{max_error_rate:.0%} in the telemetry window."
                ),
            }
        )

    tool_latency = summary.get("tool_latency") if isinstance(summary.get("tool_latency"), dict) else {}
    read_stats = tool_latency.get("telegram_read") if isinstance(tool_latency.get("telegram_read"), dict) else {}
    read_p95 = read_stats.get("p95_ms")
    if isinstance(read_p95, int | float) and read_p95 > max_read_p95:
        findings.append(
            {
                "id": "telemetry_slow_telegram_read",
                "severity": "warn",
                "message": f"telegram_read p95 {read_p95}ms exceeds {max_read_p95:g}ms threshold.",
            }
        )

    cache = summary.get("cache") if isinstance(summary.get("cache"), dict) else {}
    cache_hit_rate = cache.get("hit_rate")
    cache_total = cache.get("total")
    if not isinstance(cache_total, int | float):
        hits = cache.get("hits")
        misses = cache.get("misses")
        if isinstance(hits, int | float) or isinstance(misses, int | float):
            cache_total = float(hits or 0) + float(misses or 0)
    if (
        isinstance(cache_hit_rate, int | float)
        and isinstance(cache_total, int | float)
        and cache_total >= min_events
        and isinstance(min_cache_hit_rate, int | float)
        and cache_hit_rate < min_cache_hit_rate
    ):
        findings.append(
            {
                "id": "telemetry_low_cache_hit_rate",
                "severity": "warn",
                "message": (
                    f"Cache hit rate {float(cache_hit_rate):.0%} is below "
                    f"{float(min_cache_hit_rate):.0%} while cache events are present."
                ),
                "hit_rate": cache_hit_rate,
                "threshold": min_cache_hit_rate,
            }
        )

    prewarm = summary.get("prewarm") if isinstance(summary.get("prewarm"), dict) else {}
    prewarm_count = prewarm.get("count") or prewarm.get("total")
    prewarm_failed = prewarm.get("failed") or prewarm.get("failures") or prewarm.get("fail")
    prewarm_failure_rate = prewarm.get("failure_rate")
    if not isinstance(prewarm_failure_rate, int | float) and isinstance(prewarm_count, int | float) and prewarm_count > 0:
        prewarm_failure_rate = float(prewarm_failed or 0) / float(prewarm_count)
    if (
        isinstance(prewarm_failure_rate, int | float)
        and isinstance(prewarm_count, int | float)
        and prewarm_count > 0
        and isinstance(max_prewarm_failure_rate, int | float)
        and prewarm_failure_rate > max_prewarm_failure_rate
    ):
        findings.append(
            {
                "id": "telemetry_high_prewarm_failure_rate",
                "severity": "warn",
                "message": (
                    f"Prewarm failure rate {float(prewarm_failure_rate):.0%} exceeds "
                    f"{float(max_prewarm_failure_rate):.0%}."
                ),
                "failure_rate": prewarm_failure_rate,
                "threshold": max_prewarm_failure_rate,
            }
        )

    max_stats_age = thresholds.get("max_stats_age_seconds")
    if (
        isinstance(stats_file_age_seconds, int | float)
        and isinstance(max_stats_age, int | float)
        and stats_file_age_seconds > max_stats_age
    ):
        findings.append(
            {
                "id": "telemetry_stats_snapshot_stale",
                "severity": "warn",
                "message": (
                    f"Telemetry stats snapshot is {stats_file_age_seconds:.0f}s old; "
                    f"threshold is {float(max_stats_age):.0f}s."
                ),
            }
        )

    agent_preflight = summary.get("agent_preflight") if isinstance(summary.get("agent_preflight"), dict) else {}
    preflight_violations = agent_preflight.get("preflight_violations")
    max_preflight = thresholds.get("max_preflight_violations")
    if isinstance(preflight_violations, int) and isinstance(max_preflight, int) and preflight_violations > max_preflight:
        findings.append(
            {
                "id": "telemetry_preflight_violations",
                "severity": "warn",
                "message": (
                    f"Recorded {preflight_violations} preflight violations "
                    f"(diagnostic/tool calls before first live read); threshold is {max_preflight}."
                ),
            }
        )

    read_floodwait_events = 0
    for bucket in tool_error_buckets:
        if not isinstance(bucket, dict):
            continue
        if str(bucket.get("tool")) not in READ_TOOLS:
            continue
        if str(bucket.get("error_type") or "") not in {"FloodWaitError", "PeerFloodError"}:
            continue
        count = bucket.get("count")
        read_floodwait_events += int(count) if isinstance(count, int | float) else 1
    if isinstance(max_read_floodwait_events, int | float) and read_floodwait_events > max_read_floodwait_events:
        findings.append(
            {
                "id": "telemetry_read_floodwait",
                "severity": "warn",
                "message": (
                    f"Read-side Telegram calls hit FloodWait/rate limits {read_floodwait_events} times "
                    "in the telemetry window."
                ),
                "count": read_floodwait_events,
                "threshold": max_read_floodwait_events,
            }
        )

    rate_limited_lanes: list[dict[str, Any]] = []
    if isinstance(max_lane_rate_limited, int | float):
        for lane, lane_stats in stats_lanes.items():
            if not isinstance(lane_stats, dict):
                continue
            rate_limited = lane_stats.get("rate_limited")
            if isinstance(rate_limited, int | float) and rate_limited > max_lane_rate_limited:
                rate_limited_lanes.append(
                    {
                        "lane": str(lane),
                        "rate_limited": rate_limited,
                        "last_flood_wait_seconds": lane_stats.get("last_flood_wait_seconds"),
                    }
                )
    if rate_limited_lanes:
        findings.append(
            {
                "id": "telemetry_lane_rate_limited",
                "severity": "warn",
                "message": "Telemetry stats show scheduler lanes with rate-limited work.",
                "lanes": rate_limited_lanes,
                "threshold": max_lane_rate_limited,
            }
        )

    metrics_up = [item for item in metrics_targets if item.get("status") == "ok"]
    prometheus_ports = thresholds.get("prometheus_metrics_ports")
    if isinstance(prometheus_ports, list) and prometheus_ports and not metrics_up:
        findings.append(
            {
                "id": "telemetry_prometheus_down",
                "severity": "warn",
                "message": (
                    "No Telegram MCP Prometheus /metrics targets responded. "
                    "Set TELEGRAM_TELEMETRY_METRICS_PORT per LaunchAgent (e.g. 9109-9113) and restart MCP."
                ),
            }
        )

    source_counts = summary.get("source_counts") if isinstance(summary.get("source_counts"), dict) else {}
    write_operations = summary.get("write_operations") if isinstance(summary.get("write_operations"), dict) else {}
    return {
        "findings": findings,
        "events_in_window": events_in_window,
        "tool_errors": tool_errors,
        "raw_tool_errors": raw_tool_errors,
        "ignored_tool_errors": ignored_tool_errors,
        "top_tool_error_buckets": tool_error_buckets[:10],
        "top_slow_tools": top_slow_tools(tool_latency),
        "write_operations": write_operations,
        "cache_hit_rate": cache.get("hit_rate"),
        "source_counts": source_counts,
    }
