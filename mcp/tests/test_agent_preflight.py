import unittest
from unittest import mock

from telegram_mcp.agent_preflight import (
    observe_fast_read,
    observe_tool_call,
    reset_agent_preflight_state_for_tests,
)
from telegram_mcp.telemetry import (
    TelemetryRecorder,
    reset_recorder_for_tests,
    summarize_telemetry_log,
)


class AgentPreflightTests(unittest.TestCase):
    def tearDown(self) -> None:
        reset_agent_preflight_state_for_tests()
        reset_recorder_for_tests()

    def test_doctor_before_read_emits_preflight_violation(self) -> None:
        import tempfile
        from pathlib import Path

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
            with mock.patch("telegram_mcp.telemetry.get_recorder", return_value=recorder):
                observe_tool_call(tool="doctor_check", status="ok", source="mcp_tool")
                observe_tool_call(tool="telegram_read", status="ok", source="mcp_tool")

            summary = summarize_telemetry_log(log_path, window_hours=24)
            self.assertEqual(summary["agent_preflight"]["preflight_violations"], 1)
            self.assertEqual(summary["agent_preflight"]["seconds_to_first_read"]["count"], 1)

    def test_fast_read_records_seconds_to_first_read(self) -> None:
        import tempfile
        from pathlib import Path

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
            with mock.patch("telegram_mcp.telemetry.get_recorder", return_value=recorder):
                observe_fast_read(
                        tool="tg_read_today",
                        status="ok",
                        source="tg_cli",
                        duration_ms=250.0,
                    )

            summary = summarize_telemetry_log(log_path, window_hours=24)
            self.assertEqual(summary["agent_preflight"]["seconds_to_first_read"]["count"], 1)

    def test_synthetic_probe_is_counted_separately_from_agent_preflight(self) -> None:
        import tempfile
        from pathlib import Path

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
            with mock.patch("telegram_mcp.telemetry.get_recorder", return_value=recorder):
                observe_tool_call(
                    tool="get_me",
                    status="error",
                    source="control_plane",
                    traffic_class="synthetic_probe",
                )
                observe_tool_call(tool="get_me", status="error", source="mcp_tool")

            summary = summarize_telemetry_log(log_path, window_hours=24)
            self.assertEqual(summary["agent_preflight"]["preflight_violations"], 1)
            self.assertEqual(summary["agent_preflight"]["synthetic_probe_violations"], 1)


if __name__ == "__main__":
    unittest.main()
