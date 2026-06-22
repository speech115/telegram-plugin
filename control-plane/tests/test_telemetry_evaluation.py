from __future__ import annotations

from telegram_control_plane.telemetry_evaluation import evaluate_mcp_telemetry


def test_evaluate_mcp_telemetry_is_pure_warning_engine() -> None:
    report = evaluate_mcp_telemetry(
        {
            "status": "ok",
            "events_in_window": 30,
            "event_counts": {"tool_call": 30},
            "tool_errors": 9,
            "cache": {"hit_rate": 0.1, "hits": 1, "misses": 9, "total": 10},
            "source_counts": {"mcp_tool": 30},
            "tool_error_buckets": [{"tool": "telegram_read", "error_type": "FloodWaitError", "count": 2}],
            "tool_latency": {"telegram_read": {"count": 30, "p95_ms": 6000}},
            "write_operations": {"count": 1, "errors": 0},
        },
        thresholds={
            "min_events_for_rate_checks": 10,
            "max_tool_errors": 99,
            "max_tool_error_rate": 0.25,
            "max_telegram_read_p95_ms": 5000,
            "min_cache_hit_rate_when_cache_tracked": 0.2,
            "max_read_floodwait_events": 0,
            "max_stats_age_seconds": 60,
            "max_lane_rate_limited": 0,
        },
        effective_window=1,
        stats_file_age_seconds=120,
        stats_lanes={"read": {"rate_limited": 1, "last_flood_wait_seconds": 3}},
        metrics_targets=[],
    )

    finding_ids = {item["id"] for item in report["findings"]}
    assert {
        "telemetry_high_tool_error_rate",
        "telemetry_slow_telegram_read",
        "telemetry_low_cache_hit_rate",
        "telemetry_stats_snapshot_stale",
        "telemetry_read_floodwait",
        "telemetry_lane_rate_limited",
    }.issubset(finding_ids)
    assert report["events_in_window"] == 30
    assert report["top_slow_tools"][0]["tool"] == "telegram_read"


def test_evaluate_mcp_telemetry_ignores_synthetic_tool_error_buckets() -> None:
    report = evaluate_mcp_telemetry(
        {
            "status": "ok",
            "events_in_window": 40,
            "event_counts": {"tool_call": 40},
            "tool_errors": 14,
            "tool_error_buckets": [
                {"tool": "broken_tool", "error_type": "RuntimeError", "count": 12},
                {"tool": "telegram_read", "error_type": "ToolContractError", "count": 2},
            ],
        },
        thresholds={
            "min_events_for_rate_checks": 10,
            "max_tool_errors": 10,
            "max_tool_error_rate": 0.25,
            "max_telegram_read_p95_ms": 5000,
            "max_read_floodwait_events": 0,
            "max_stats_age_seconds": 60,
            "max_lane_rate_limited": 0,
        },
        effective_window=1,
        stats_file_age_seconds=10,
        stats_lanes={},
        metrics_targets=[],
    )

    finding_ids = {item["id"] for item in report["findings"]}
    assert "telemetry_high_tool_error_count" not in finding_ids
    assert report["raw_tool_errors"] == 14
    assert report["ignored_tool_errors"] == 12
    assert report["tool_errors"] == 2
    assert report["top_tool_error_buckets"] == [
        {"tool": "telegram_read", "error_type": "ToolContractError", "count": 2}
    ]
