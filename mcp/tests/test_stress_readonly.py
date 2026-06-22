import io
import json
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from telegram_mcp import stress_readonly


class FakeMcp:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    async def call_tool(self, *, tool_name, arguments, **_kwargs):
        self.calls.append((tool_name, dict(arguments)))
        if tool_name == "resolve_dialog":
            return {
                "id": 123,
                "dialog_ref": "tg://dialog/user/123",
                "name": "Smoke Chat",
                "type": "user",
                "resolved_from": "me",
                "match_confidence": 1.0,
            }, 0.01, None
        if tool_name == "get_me":
            return {"id": 1, "first_name": "Test"}, 0.01, None
        if tool_name == "collect_dialog_context":
            return {"messages": [], "message_count": 0, "collection_mode": "fast"}, 0.01, None
        if tool_name == "read_today_dialog":
            return {"messages": [], "message_count": 0}, 0.01, None
        if tool_name == "search_dialog_messages":
            return {"messages": [], "message_count": 0, "query": "."}, 0.01, None
        raise AssertionError(f"unexpected tool: {tool_name}")


class StressReadonlyTests(unittest.TestCase):
    def test_stress_readonly_uses_only_safe_readonly_calls(self):
        fake = FakeMcp()
        stdout = io.StringIO()

        with patch(
            "telegram_mcp.stress_readonly.call_tool_with_failover",
            side_effect=fake.call_tool,
        ):
            with redirect_stdout(stdout):
                exit_code = stress_readonly.main(
                    ["--iterations", "5", "--concurrency", "2", "--json"]
                )

        self.assertEqual(exit_code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["total_calls"], 5)
        for tool_name, _args in fake.calls:
            self.assertIn(
                f"telegram.{tool_name}",
                stress_readonly.READONLY_CALLS,
            )
        collect_args = [args for name, args in fake.calls if name == "collect_dialog_context"]
        self.assertTrue(collect_args)
        self.assertEqual(collect_args[0]["mode"], "fast")
        self.assertEqual(collect_args[0]["recent_limit"], 1)
        self.assertFalse(collect_args[0]["include_pinned"])
        self.assertFalse(collect_args[0]["include_voice_transcription"])

    def test_cache_pair_mode_repeats_identical_facade_calls(self):
        fake = FakeMcp()
        stdout = io.StringIO()

        with patch(
            "telegram_mcp.stress_readonly.call_tool_with_failover",
            side_effect=fake.call_tool,
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

        calls_without_discovery = [
            item for item in fake.calls if item[0] != "resolve_dialog"
        ]
        self.assertEqual(len(calls_without_discovery), 6)
        for first, second in zip(calls_without_discovery[0::2], calls_without_discovery[1::2], strict=True):
            self.assertEqual(first, second)
        self.assertEqual(calls_without_discovery[0][0], "collect_dialog_context")
        self.assertEqual(calls_without_discovery[2][0], "read_today_dialog")
        self.assertEqual(calls_without_discovery[4][0], "search_dialog_messages")


if __name__ == "__main__":
    unittest.main()
