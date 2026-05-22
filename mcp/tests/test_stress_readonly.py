import io
import json
import os
import stat
import tempfile
import textwrap
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from telegram_mcp import stress_readonly


class StressReadonlyTests(unittest.TestCase):
    def _write_fake_mcporter(self, root: Path) -> Path:
        fake = root / "mcporter"
        fake.write_text(
            textwrap.dedent(
                """\
                #!/bin/sh
                printf '%s\\n' "$*" >> "${CALL_LOG}"
                if [ "$1" = "call" ] && [ "$2" = "telegram.list_chats" ]; then
                  echo '{"dialogs":[{"id":123,"dialog_ref":"tg://dialog/user/123","name":"Smoke Chat"}]}'
                  exit 0
                fi
                if [ "$1" = "call" ] && [ "$2" = "telegram.collect_dialog_context" ]; then
                  echo '{"messages":[],"message_count":0,"collection_mode":"fast"}'
                  exit 0
                fi
                if [ "$1" = "call" ] && [ "$2" = "telegram.read_today_dialog" ]; then
                  echo '{"messages":[],"message_count":0}'
                  exit 0
                fi
                if [ "$1" = "call" ] && [ "$2" = "telegram.search_dialog_messages" ]; then
                  echo '{"messages":[],"message_count":0,"query":"."}'
                  exit 0
                fi
                if [ "$1" = "call" ] && [ "$2" = "telegram.get_me" ]; then
                  echo '{"id":1,"first_name":"Test"}'
                  exit 0
                fi
                echo "unexpected args: $*" >&2
                exit 64
                """
            ),
            encoding="utf-8",
        )
        fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
        return fake

    def test_stress_readonly_uses_only_safe_readonly_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake_mcporter = self._write_fake_mcporter(root)
            call_log = root / "calls.log"
            stdout = io.StringIO()

            with patch.dict(
                os.environ,
                {
                    "MCPORTER_BIN": str(fake_mcporter),
                    "CALL_LOG": str(call_log),
                },
            ):
                with redirect_stdout(stdout):
                    exit_code = stress_readonly.main(
                        ["--iterations", "5", "--concurrency", "2", "--json"]
                    )

            self.assertEqual(exit_code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["status"], "ok")
            self.assertEqual(payload["total_calls"], 5)
            lines = call_log.read_text(encoding="utf-8").strip().splitlines()
            self.assertTrue(lines)
            for line in lines:
                self.assertRegex(
                    line,
                    r"^call telegram\.(get_me|list_chats|collect_dialog_context|read_today_dialog|search_dialog_messages)\b",
                )
            self.assertTrue(
                any(
                    "telegram.collect_dialog_context" in line
                    and "mode=fast" in line
                    and "recent_limit=1" in line
                    and "include_pinned=false" in line
                    and "include_voice_transcription=false" in line
                    for line in lines
                )
            )
            self.assertTrue(
                any(
                    "telegram.read_today_dialog" in line
                    and "include_voice_transcription=false" in line
                    and "include_sender_name=false" in line
                    for line in lines
                )
            )
            self.assertTrue(
                any(
                    "telegram.search_dialog_messages" in line
                    and "query=." in line
                    and "limit=1" in line
                    and "include_sender_name=false" in line
                    for line in lines
                )
            )

    def test_cache_pair_mode_repeats_identical_facade_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake_mcporter = self._write_fake_mcporter(root)
            call_log = root / "calls.log"
            stdout = io.StringIO()

            with patch.dict(
                os.environ,
                {
                    "MCPORTER_BIN": str(fake_mcporter),
                    "CALL_LOG": str(call_log),
                },
            ):
                with redirect_stdout(stdout):
                    exit_code = stress_readonly.main(
                        [
                            "--iterations",
                            "6",
                            "--mode",
                            "cache-pair",
                            "--concurrency",
                            "4",
                            "--json",
                        ]
                    )

            self.assertEqual(exit_code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["status"], "ok")
            self.assertEqual(payload["mode"], "cache-pair")
            self.assertEqual(payload["total_calls"], 6)
            self.assertEqual(len(payload["cache_pairs"]), 3)
            for pair in payload["cache_pairs"]:
                self.assertIn("first", pair)
                self.assertIn("second", pair)
                self.assertIn("delta_ms", pair)

            lines = [
                line
                for line in call_log.read_text(encoding="utf-8").strip().splitlines()
                if not line.startswith("call telegram.list_chats")
            ]
            self.assertEqual(len(lines), 6)
            for first, second in zip(lines[0::2], lines[1::2], strict=True):
                self.assertEqual(first, second)
            self.assertIn("telegram.collect_dialog_context", lines[0])
            self.assertIn("telegram.read_today_dialog", lines[2])
            self.assertIn("telegram.search_dialog_messages", lines[4])
