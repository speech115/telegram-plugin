import unittest
from unittest.mock import AsyncMock, patch

from telegram_mcp.tg_cli import _wrap_ok, cmd_count_posts, route_task


class TgCliTests(unittest.TestCase):
    def test_wrap_ok_marks_tool_error_payload_as_failure(self):
        payload = _wrap_ok(
            command="read today",
            endpoint="http://127.0.0.1:8799/mcp",
            endpoint_port=8799,
            elapsed_seconds=0.1,
            payload="Error executing tool telegram_read: raw failure",
            intent="live_today",
        )

        self.assertIs(payload["ok"], False)
        self.assertEqual(payload["error"], "telegram_tool_error")
        self.assertEqual(payload["data_source"], "live_telegram")
        self.assertEqual(payload["tool_error_payload"], "Error executing tool telegram_read: raw failure")

    def test_route_task_plans_channel_post_count_without_execution(self):
        payload = route_task("@sral_v_nastav сколько постов в этом канале всего?")

        self.assertEqual(payload["intent"], "count_channel_posts")
        self.assertEqual(payload["tool"], "telegram_count_posts")
        self.assertEqual(payload["execute"], ["tg", "count", "posts", "@sral_v_nastav", "--json"])
        self.assertFalse(payload["needs_user_input"])

    def test_count_posts_calls_readonly_mcp_tool(self):
        async def fake_call_tool_with_failover(**kwargs):
            self.assertEqual(kwargs["tool_name"], "telegram_count_posts")
            self.assertEqual(kwargs["arguments"], {"chat": "@sral_v_nastav"})
            return (
                {"total": 123, "data_source": "live_telegram"},
                0.1,
                type(
                    "Attempt",
                    (),
                    {"endpoint": "http://127.0.0.1:8799/mcp", "port": 8799},
                )(),
            )

        with patch("telegram_mcp.tg_cli.call_tool_with_failover", AsyncMock(side_effect=fake_call_tool_with_failover)):
            with patch("telegram_mcp.tg_cli.record_telemetry"):
                import asyncio

                payload = asyncio.run(
                    cmd_count_posts(
                        chat="@sral_v_nastav",
                        timeout=5,
                        endpoint=None,
                        env_file=None,
                        account="main",
                    )
                )

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["intent"], "count_channel_posts")
        self.assertEqual(payload["payload"]["total"], 123)
