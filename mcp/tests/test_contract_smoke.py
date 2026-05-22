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

from telegram_mcp import contract_smoke


class ContractSmokeTests(unittest.TestCase):
    def _write_fake_mcporter(
        self,
        root: Path,
        *,
        bad_prepare_shape: bool = False,
        truncated_list_json: bool = False,
    ) -> Path:
        fake = root / "mcporter"
        json_catalog = (
            '{"tools":['
            if truncated_list_json
            else '{"tools":[{"name":"telegram.collect_dialog_context"},{"name":"telegram.prepare_dialog_reply"},{"name":"telegram.resolve_dialog"},{"name":"telegram.search_dialog_messages"},{"name":"telegram.find_dialog"},{"name":"telegram.read_dialog"},{"name":"telegram.collect_context"},{"name":"telegram.draft_reply"},{"name":"telegram.prepare_send_message"},{"name":"telegram.prepare_reply_message"},{"name":"telegram.prepare_media_inspection_manifest"}]}'
        )
        prepare_payload = (
            '{"chat":{"id":123},"context":{},"preview_only":false,'
            '"send_tool":"send_dialog_message","send_args_preview":{}}'
            if bad_prepare_shape
            else '{"chat":{"id":123},"goal":"contract smoke preview only",'
            '"context":{"chat":{"id":123},"messages":[],"message_count":0,'
            '"collection_mode":"fast"},"preview_only":true,'
            '"send_tool":"send_dialog_message","send_args_preview":{}}'
        )
        fake.write_text(
            textwrap.dedent(
                f"""\
                #!/bin/sh
                printf '%s\\n' "$*" >> "${{CALL_LOG}}"
                if [ "$1" = "list" ] && [ "$2" = "telegram" ] && [ "${{3:-}}" = "--json" ]; then
                  echo '{json_catalog}'
                  exit 0
                fi
                if [ "$1" = "list" ] && [ "$2" = "telegram" ]; then
                  printf '%s\\n' 'function collect_dialog_context(chat: unknown);'
                  printf '%s\\n' 'function prepare_dialog_reply(chat: unknown, goal: string);'
                  printf '%s\\n' 'function resolve_dialog(query: unknown);'
                  printf '%s\\n' 'function search_dialog_messages(chat: unknown, query: string);'
                  printf '%s\\n' 'function find_dialog(query: unknown);'
                  printf '%s\\n' 'function read_dialog(chat: unknown);'
                  printf '%s\\n' 'function collect_context(chat: unknown);'
                  printf '%s\\n' 'function draft_reply(chat: unknown, goal: string);'
                  printf '%s\\n' 'function prepare_send_message(chat: unknown, text: string);'
                  printf '%s\\n' 'function prepare_reply_message(chat: unknown, message_id: number, text: string);'
                  printf '%s\\n' 'function prepare_media_inspection_manifest(chat: unknown);'
                  exit 0
                fi
                if [ "$1" = "call" ] && [ "$2" = "telegram.resolve_dialog" ]; then
                  echo '{{"id":123,"dialog_ref":"tg://dialog/user/123","name":"Smoke Chat","type":"user","resolved_from":"me","match_confidence":1.0}}'
                  exit 0
                fi
                if [ "$1" = "call" ] && [ "$2" = "telegram.collect_dialog_context" ]; then
                  echo '{{"chat":{{"id":123,"dialog_ref":"tg://dialog/user/123"}},"messages":[],"message_count":0,"collection_mode":"fast"}}'
                  exit 0
                fi
                if [ "$1" = "call" ] && [ "$2" = "telegram.collect_context" ]; then
                  echo '{{"chat":{{"id":123,"dialog_ref":"tg://dialog/user/123"}},"messages":[],"message_count":0,"collection_mode":"fast"}}'
                  exit 0
                fi
                if [ "$1" = "call" ] && [ "$2" = "telegram.prepare_dialog_reply" ]; then
                  echo '{prepare_payload}'
                  exit 0
                fi
                if [ "$1" = "call" ] && [ "$2" = "telegram.draft_reply" ]; then
                  echo '{prepare_payload}'
                  exit 0
                fi
                if [ "$1" = "call" ] && [ "$2" = "telegram.search_dialog_messages" ]; then
                  echo '{{"chat":{{"id":123,"dialog_ref":"tg://dialog/user/123"}},"messages":[],"message_count":0}}'
                  exit 0
                fi
                if [ "$1" = "call" ] && [ "$2" = "telegram.find_dialog" ]; then
                  echo '{{"id":123,"dialog_ref":"tg://dialog/user/123","name":"Smoke Chat","type":"user","resolved_from":"tg://dialog/user/123","match_confidence":1.0}}'
                  exit 0
                fi
                if [ "$1" = "call" ] && [ "$2" = "telegram.prepare_send_message" ]; then
                  echo '{{"chat":{{"id":123,"dialog_ref":"tg://dialog/user/123"}},"text":"contract smoke preview only","preview_only":true,"send_tool":"send_dialog_message","send_args_preview":{{"chat":"tg://dialog/user/123","text":"contract smoke preview only"}}}}'
                  exit 0
                fi
                if [ "$1" = "call" ] && [ "$2" = "telegram.prepare_reply_message" ]; then
                  echo '{{"chat":{{"id":123,"dialog_ref":"tg://dialog/user/123"}},"text":"contract smoke reply preview only","reply_target_message_id":1,"preview_only":true,"send_tool":"reply_in_dialog","send_args_preview":{{"chat":"tg://dialog/user/123","message_id":1,"text":"contract smoke reply preview only"}}}}'
                  exit 0
                fi
                if [ "$1" = "call" ] && [ "$2" = "telegram.read_dialog" ]; then
                  echo '{{"chat":{{"id":123,"dialog_ref":"tg://dialog/user/123"}},"messages":[],"message_count":0}}'
                  exit 0
                fi
                if [ "$1" = "call" ] && [ "$2" = "telegram.prepare_media_inspection_manifest" ]; then
                  echo '{{"chat":{{"id":123,"dialog_ref":"tg://dialog/user/123"}},"items":[],"media_count":0,"download_tool":"download_dialog_media"}}'
                  exit 0
                fi
                if [ "$1" = "call" ] && [ "$2" = "telegram.doctor_check" ]; then
                  count_file="${{STATS_COUNT_FILE}}"
                  count=0
                  if [ -f "$count_file" ]; then count="$(cat "$count_file")"; fi
                  next=$((count + 1))
                  printf '%s' "$next" > "$count_file"
                  if [ "$count" -eq 0 ]; then
                    echo '{{"status":"ok","runtime_stats":{{"dialog_read_cache_hit":0,"dialog_search_cache_hit":0}}}}'
                  else
                    echo '{{"status":"ok","runtime_stats":{{"dialog_read_cache_hit":1,"dialog_search_cache_hit":1}}}}'
                  fi
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

    def test_contract_smoke_runs_safe_external_contract_calls(self):
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
                    exit_code = contract_smoke.main(["--json"])

            self.assertEqual(exit_code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["status"], "ok")
            self.assertEqual(payload["profile"], "core")
            self.assertEqual(payload["dialog"], "tg://dialog/user/123")
            self.assertEqual(
                payload["listed_tools"],
                [
                    "collect_dialog_context",
                    "prepare_dialog_reply",
                    "resolve_dialog",
                    "search_dialog_messages",
                ],
            )

            lines = call_log.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(lines[0], "list telegram --json")
            self.assertIn("call telegram.resolve_dialog query=me", lines[1])
            collect_lines = [
                line for line in lines if line.startswith("call telegram.collect_dialog_context ")
            ]
            self.assertEqual(len(collect_lines), 2)
            for line in collect_lines:
                self.assertIn("mode=fast", line)
                self.assertIn("recent_limit=1", line)
                self.assertIn("include_pinned=false", line)
                self.assertIn("include_voice_transcription=false", line)
            self.assertTrue(
                any(
                    line.startswith("call telegram.prepare_dialog_reply ")
                    and "goal=contract smoke preview only" in line
                    and "context_limit=1" in line
                    for line in lines
                )
            )
            self.assertTrue(
                any(
                    line.startswith("call telegram.search_dialog_messages ")
                    and "query=a" in line
                    and "limit=1" in line
                    and "include_sender_name=false" in line
                    for line in lines
                )
            )
            self.assertFalse(any("send_dialog_message" in line for line in lines))
            self.assertFalse(any("reply_in_dialog" in line for line in lines))

    def test_contract_smoke_falls_back_to_text_tool_catalog(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake_mcporter = self._write_fake_mcporter(root, truncated_list_json=True)
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
                    exit_code = contract_smoke.main(["--json"])

            self.assertEqual(exit_code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["status"], "ok")
            lines = call_log.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(lines[0], "list telegram --json")
            self.assertEqual(lines[1], "list telegram")

    def test_contract_smoke_app_media_profile_checks_readonly_aliases(self):
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
                    "STATS_COUNT_FILE": str(root / "stats-count"),
                },
            ):
                with redirect_stdout(stdout):
                    exit_code = contract_smoke.main(
                        ["--profile", "app-media", "--json"]
                    )

            self.assertEqual(exit_code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["profile"], "app-media")
            lines = call_log.read_text(encoding="utf-8").strip().splitlines()
            self.assertTrue(any("telegram.find_dialog" in line for line in lines))
            self.assertTrue(any("telegram.read_dialog" in line for line in lines))
            self.assertTrue(any("telegram.collect_context" in line for line in lines))
            self.assertTrue(any("telegram.draft_reply" in line for line in lines))
            self.assertTrue(any("telegram.prepare_send_message" in line for line in lines))
            self.assertTrue(any("telegram.prepare_reply_message" in line for line in lines))
            self.assertTrue(
                any("telegram.prepare_media_inspection_manifest" in line for line in lines)
            )
            self.assertFalse(any("send_dialog_message" in line for line in lines))

    def test_contract_smoke_cache_stats_proof_checks_hit_counters(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake_mcporter = self._write_fake_mcporter(root)
            stdout = io.StringIO()

            with patch.dict(
                os.environ,
                {
                    "MCPORTER_BIN": str(fake_mcporter),
                    "CALL_LOG": str(root / "calls.log"),
                    "STATS_COUNT_FILE": str(root / "stats-count"),
                },
            ):
                with redirect_stdout(stdout):
                    exit_code = contract_smoke.main(["--check-cache-stats", "--json"])

            self.assertEqual(exit_code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(
                payload["cache_stats_delta"],
                {
                    "dialog_read_cache_hit": 1,
                    "dialog_search_cache_hit": 1,
                },
            )

    def test_contract_smoke_rejects_non_preview_prepare_shape(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake_mcporter = self._write_fake_mcporter(root, bad_prepare_shape=True)
            stdout = io.StringIO()

            with patch.dict(
                os.environ,
                {
                    "MCPORTER_BIN": str(fake_mcporter),
                    "CALL_LOG": str(root / "calls.log"),
                },
            ):
                with redirect_stdout(stdout):
                    exit_code = contract_smoke.main(["--json"])

            self.assertEqual(exit_code, 1)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["status"], "error")
            self.assertIn("preview-only", payload["error"])

    def test_contract_smoke_rejects_missing_required_tool(self):
        payload = {
            "tools": [
                {"name": "telegram.collect_dialog_context"},
                {"name": "telegram.prepare_dialog_reply"},
            ]
        }

        with self.assertRaisesRegex(
            contract_smoke.ContractSmokeError,
            "search_dialog_messages",
        ):
            contract_smoke._require_tools(payload)


if __name__ == "__main__":
    unittest.main()
