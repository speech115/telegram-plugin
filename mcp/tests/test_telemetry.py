import json
import tempfile
import unittest
from pathlib import Path

from telegram_mcp.telemetry import (
    TelemetryRecorder,
    reset_recorder_for_tests,
    summarize_telemetry_log,
    telemetry_fields_from_kwargs,
)


class TelemetryTests(unittest.TestCase):
    def tearDown(self) -> None:
        reset_recorder_for_tests()

    def test_record_and_summarize_tool_latency(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "telemetry.jsonl"
            recorder = TelemetryRecorder(
                enabled=True,
                log_dir=log_path.parent,
                legacy_log_path=log_path,
                stats_path=Path(tmp) / "stats.json",
                stats_flush_seconds=0,
                daily_rotation=False,
                retention_days=30,
                prometheus_enabled=False,
                transport="streamable-http",
                port=8799,
            )
            recorder.record(
                "tool_call",
                tool="telegram_read",
                status="ok",
                duration_ms=120.0,
                result_cache_hit=False,
            )
            recorder.record(
                "tool_call",
                tool="telegram_read",
                status="ok",
                duration_ms=40.0,
                result_cache_hit=True,
            )
            recorder.record("cache_access", cache_kind="dialog_read", outcome="miss")

            summary = summarize_telemetry_log(log_path, window_hours=24)
            self.assertEqual(summary["status"], "ok")
            self.assertEqual(summary["events_in_window"], 3)
            self.assertEqual(summary["tool_latency"]["telegram_read"]["count"], 2)
            self.assertEqual(summary["cache"]["hits"], 1)
            self.assertEqual(summary["cache"]["misses"], 2)

    def test_kwargs_redact_sensitive_fields(self) -> None:
        safe = telemetry_fields_from_kwargs(
            {
                "chat": "me",
                "text": "secret message",
                "limit": 10,
            }
        )
        self.assertEqual(safe["arg_chat"], "me")
        self.assertEqual(safe["arg_limit"], 10)
        self.assertNotIn("arg_text", safe)

    def test_summarize_missing_log(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            summary = summarize_telemetry_log(Path(tmp) / "missing.jsonl")
            self.assertEqual(summary["status"], "missing")

    def test_summarize_counts_current_read_completed_event(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "telemetry.jsonl"
            recorder = TelemetryRecorder(
                enabled=True,
                log_dir=log_path.parent,
                legacy_log_path=log_path,
                stats_path=Path(tmp) / "stats.json",
                stats_flush_seconds=0,
                daily_rotation=False,
                retention_days=30,
                prometheus_enabled=False,
                transport="streamable-http",
                port=8799,
            )

            recorder.record("telegram_read_completed", result_cache_hit=False)

            summary = summarize_telemetry_log(log_path, window_hours=24)
            self.assertEqual(summary["cache"]["misses"], 1)

    def test_summarize_groups_tool_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "telemetry.jsonl"
            recorder = TelemetryRecorder(
                enabled=True,
                log_dir=log_path.parent,
                legacy_log_path=log_path,
                stats_path=Path(tmp) / "stats.json",
                stats_flush_seconds=0,
                daily_rotation=False,
                retention_days=30,
                prometheus_enabled=False,
                transport="streamable-http",
                port=8800,
            )

            recorder.record(
                "tool_call",
                tool="get_me",
                status="error",
                duration_ms=5.0,
                error_type="TypeNotFoundError",
            )
            recorder.record(
                "tool_call",
                tool="get_me",
                status="error",
                duration_ms=1.0,
                error_type="ToolContractError",
                error_code="circuit_open",
            )

            summary = summarize_telemetry_log(log_path, window_hours=24)
            self.assertEqual(summary["tool_errors_by_tool"]["get_me"], 2)
            self.assertEqual(
                summary["tool_error_buckets"][0],
                {
                    "tool": "get_me",
                    "error_type": "ToolContractError",
                    "error_code": "circuit_open",
                    "port": 8800,
                    "count": 1,
                },
            )

    def test_summarize_write_operations(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "telemetry.jsonl"
            recorder = TelemetryRecorder(
                enabled=True,
                log_dir=log_path.parent,
                legacy_log_path=log_path,
                stats_path=Path(tmp) / "stats.json",
                stats_flush_seconds=0,
                daily_rotation=False,
                retention_days=30,
                prometheus_enabled=False,
                transport="streamable-http",
                port=8799,
            )

            recorder.record(
                "write_operation",
                operation="send_message",
                lane="write",
                status="started",
                duration_ms=1.0,
            )
            recorder.record(
                "write_operation",
                operation="send_message",
                lane="write",
                status="succeeded",
                duration_ms=20.0,
            )
            recorder.record(
                "write_operation",
                operation="send_message",
                lane="write",
                status="failed",
                duration_ms=40.0,
                error_type="ToolContractError",
                error_code="permission_denied",
            )

            summary = summarize_telemetry_log(log_path, window_hours=24)
            self.assertEqual(summary["write_operations"]["count"], 3)
            self.assertEqual(summary["write_operations"]["errors"], 1)
            self.assertEqual(summary["write_operations"]["by_operation"]["send_message"]["count"], 3)
            self.assertEqual(summary["write_operations"]["latency"]["send_message"]["p95_ms"], 40.0)


if __name__ == "__main__":
    unittest.main()
