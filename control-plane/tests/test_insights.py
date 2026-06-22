from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import telegram_control_plane.insights as insights

ROOT = Path(__file__).resolve().parents[1]


def test_build_insights_ranks_actionable_telemetry(monkeypatch, tmp_path: Path) -> None:
    stats = tmp_path / "telemetry-stats.json"
    stats.write_text(
        json.dumps(
            {
                "runtime_stats": {
                    "lanes": {
                        "read": {"count": 20, "rate_limited": 2, "p95_duration_ms": 8000},
                        "media": {"count": 5, "rate_limited": 0, "max_queue_wait_ms": 1200},
                    }
                }
            }
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(insights, "MCP_TELEMETRY_STATS", stats)
    monkeypatch.setattr(
        insights,
        "audit_mcp_telemetry",
        lambda window_hours=None: {
            "status": "warn",
            "events_in_window": 42,
            "cache_hit_rate": 0.1,
            "top_slow_tools": [
                {"tool": "download_media", "count": 1, "p95_ms": 42000, "max_ms": 42000},
                {"tool": "tg_read_today", "count": 4, "p95_ms": 9000, "max_ms": 11000},
                {"tool": "telegram_read", "count": 10, "p95_ms": 5000, "max_ms": 7000},
            ],
            "top_tool_error_buckets": [
                {"tool": "telegram_read", "error_type": "FloodWaitError", "error_code": "rate_limited", "port": 8799, "count": 3},
                {"tool": "telegram_read", "error_type": "FloodWaitError", "error_code": "rate_limited", "port": 8800, "count": 2},
            ],
            "findings": [
                {"id": "telemetry_low_cache_hit_rate", "severity": "warn", "message": "cache low"}
            ],
        },
    )

    report = insights.build_insights(window_hours=6)

    assert report["status"] == "warn"
    assert report["window_hours"] == 6
    assert report["recommendations"][0]["kind"] == "slow_tool"
    assert report["recommendations"][0]["subject"] == "download_media"
    assert "manifest" in report["recommendations"][0]["recommendation"]
    floodwait = next(item for item in report["recommendations"] if item["kind"] == "floodwait")
    assert floodwait["count"] == 5
    assert floodwait["ports"] == [8799, 8800]
    assert any(item["kind"] == "lane_pressure" and item["subject"] == "read" for item in report["recommendations"])


def test_build_insights_keeps_ok_status_for_advisory_recommendations(monkeypatch, tmp_path: Path) -> None:
    stats = tmp_path / "telemetry-stats.json"
    stats.write_text('{"runtime_stats": {}}\n', encoding="utf-8")
    monkeypatch.setattr(insights, "MCP_TELEMETRY_STATS", stats)
    monkeypatch.setattr(
        insights,
        "audit_mcp_telemetry",
        lambda window_hours=None: {
            "status": "ok",
            "events_in_window": 10,
            "cache_hit_rate": 0.7,
            "top_slow_tools": [{"tool": "telegram_read", "count": 2, "p95_ms": 1000}],
            "top_tool_error_buckets": [],
            "findings": [],
        },
    )

    report = insights.build_insights()

    assert report["status"] == "ok"
    assert report["findings"] == []
    assert report["recommendations"][0]["kind"] == "slow_tool"


def test_build_insights_propagates_blocking_telemetry_status(monkeypatch, tmp_path: Path) -> None:
    stats = tmp_path / "telemetry-stats.json"
    stats.write_text('{"runtime_stats": {}}\n', encoding="utf-8")
    monkeypatch.setattr(insights, "MCP_TELEMETRY_STATS", stats)
    monkeypatch.setattr(
        insights,
        "audit_mcp_telemetry",
        lambda window_hours=None: {
            "status": "fail",
            "events_in_window": 0,
            "cache_hit_rate": None,
            "top_slow_tools": [],
            "top_tool_error_buckets": [],
            "findings": [
                {"id": "telemetry_log_missing", "severity": "blocking", "message": "missing"}
            ],
        },
    )

    report = insights.build_insights()

    assert report["status"] == "fail"
    assert report["findings"][0]["id"] == "telemetry_log_missing"


def test_telegram_insights_cli_emits_json() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "telegram_control_plane", "insights", "--json"],
        cwd=ROOT,
        env={"PYTHONPATH": str(ROOT / "src")},
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=90,
        check=False,
    )

    assert result.returncode in {0, 1}
    payload = json.loads(result.stdout)
    assert payload["command"] == "insights"
    assert "recommendations" in payload
