import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from telegram_mcp.telemetry import TelemetryRecorder, resolve_log_sources, summarize_telemetry_log


class TelemetryRotationTests(unittest.TestCase):
    def test_writes_daily_file_and_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            log_dir = root / "telemetry"
            legacy = root / "telemetry.jsonl"
            recorder = TelemetryRecorder(
                enabled=True,
                log_dir=log_dir,
                legacy_log_path=legacy,
                stats_path=root / "stats.json",
                stats_flush_seconds=0,
                daily_rotation=True,
                retention_days=30,
                prometheus_enabled=False,
                transport="streamable-http",
                port=8799,
            )
            recorder.record("tool_call", tool="telegram_read", status="ok", duration_ms=10.0)
            daily = log_dir / "daily" / f"{date.today().isoformat()}.jsonl"
            self.assertTrue(daily.exists())
            self.assertTrue(legacy.is_symlink())
            self.assertEqual(legacy.resolve(), daily.resolve())

    def test_prunes_old_daily_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            log_dir = root / "telemetry"
            daily = log_dir / "daily"
            daily.mkdir(parents=True)
            old_day = (date.today() - timedelta(days=40)).isoformat()
            stale = daily / f"{old_day}.jsonl"
            stale.write_text('{"ts":"2020-01-01T00:00:00Z","event":"tool_call"}\n', encoding="utf-8")
            recorder = TelemetryRecorder(
                enabled=True,
                log_dir=log_dir,
                legacy_log_path=root / "telemetry.jsonl",
                stats_path=root / "stats.json",
                stats_flush_seconds=0,
                daily_rotation=True,
                retention_days=30,
                prometheus_enabled=False,
                transport="stdio",
                port=None,
            )
            recorder.record("tool_call", tool="get_me", status="ok")
            self.assertFalse(stale.exists())

    def test_summarize_reads_daily_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            log_dir = root / "telemetry"
            daily = log_dir / "daily"
            daily.mkdir(parents=True)
            path = daily / f"{date.today().isoformat()}.jsonl"
            path.write_text(
                json.dumps(
                    {
                        "ts": "2099-01-01T12:00:00Z",
                        "event": "tool_call",
                        "tool": "telegram_read",
                        "status": "ok",
                        "duration_ms": 50,
                        "source": "mcp_tool",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            sources = resolve_log_sources(log_dir=log_dir)
            self.assertTrue(sources)
            summary = summarize_telemetry_log(log_dir=log_dir, window_hours=24 * 365)
            self.assertEqual(summary["status"], "ok")
            self.assertEqual(summary["events_in_window"], 1)
            self.assertEqual(summary["source_counts"]["mcp_tool"], 1)


if __name__ == "__main__":
    unittest.main()