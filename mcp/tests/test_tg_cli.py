import unittest
from unittest.mock import AsyncMock, patch

from telegram_mcp.metadata_tools_spec import COUNT_SPECS_BY_CLI, LIST_SPECS_BY_CLI
from telegram_mcp.tg_cli import _wrap_ok, cmd_count_metadata, cmd_count_posts, cmd_list_metadata, route_task


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

    def test_route_task_plans_filtered_metadata_count(self):
        payload = route_task("@sral_v_nastav сколько видео в этом канале?")

        self.assertEqual(payload["intent"], "count_channel_videos")
        self.assertEqual(payload["tool"], "telegram_count_videos")
        self.assertEqual(payload["execute"], ["tg", "count", "videos", "@sral_v_nastav", "--json"])

    def test_route_task_plans_bounded_metadata_list(self):
        payload = route_task("@sral_v_nastav покажи ссылки")

        self.assertEqual(payload["intent"], "list_channel_links")
        self.assertEqual(payload["tool"], "telegram_list_links")
        self.assertEqual(payload["execute"], ["tg", "list", "links", "@sral_v_nastav", "--limit", "20", "--json"])

    def test_route_task_plans_latest_info_and_message_by_id(self):
        latest = route_task("@sral_v_nastav последний пост")
        self.assertEqual(latest["tool"], "telegram_latest_message")
        self.assertEqual(latest["execute"], ["tg", "latest", "@sral_v_nastav", "--json"])

        info = route_task("@sral_v_nastav инфо о канале")
        self.assertEqual(info["tool"], "telegram_dialog_metadata")
        self.assertEqual(info["execute"], ["tg", "info", "@sral_v_nastav", "--json"])

        message = route_task("@sral_v_nastav message 42")
        self.assertEqual(message["tool"], "telegram_get_message")
        self.assertEqual(message["execute"], ["tg", "message", "@sral_v_nastav", "42", "--json"])

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

    def test_count_metadata_uses_spec_tool(self):
        async def fake_call_tool_with_failover(**kwargs):
            self.assertEqual(kwargs["tool_name"], "telegram_count_videos")
            self.assertEqual(kwargs["arguments"], {"chat": "@sral_v_nastav"})
            return (
                {"total": 7, "data_source": "live_telegram"},
                0.1,
                type("Attempt", (), {"endpoint": "http://127.0.0.1:8799/mcp", "port": 8799})(),
            )

        with patch("telegram_mcp.tg_cli.call_tool_with_failover", AsyncMock(side_effect=fake_call_tool_with_failover)):
            with patch("telegram_mcp.tg_cli.record_telemetry"):
                import asyncio

                payload = asyncio.run(
                    cmd_count_metadata(
                        chat="@sral_v_nastav",
                        spec=COUNT_SPECS_BY_CLI["videos"],
                        timeout=5,
                        endpoint=None,
                        env_file=None,
                        account="main",
                    )
                )

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["intent"], "count_channel_videos")

    def test_list_metadata_uses_spec_tool(self):
        async def fake_call_tool_with_failover(**kwargs):
            self.assertEqual(kwargs["tool_name"], "telegram_list_links")
            self.assertEqual(kwargs["arguments"], {"chat": "@sral_v_nastav", "limit": 10, "offset_id": 42})
            return (
                {"message_count": 2, "data_source": "live_telegram"},
                0.1,
                type("Attempt", (), {"endpoint": "http://127.0.0.1:8799/mcp", "port": 8799})(),
            )

        with patch("telegram_mcp.tg_cli.call_tool_with_failover", AsyncMock(side_effect=fake_call_tool_with_failover)):
            with patch("telegram_mcp.tg_cli.record_telemetry"):
                import asyncio

                payload = asyncio.run(
                    cmd_list_metadata(
                        chat="@sral_v_nastav",
                        spec=LIST_SPECS_BY_CLI["links"],
                        limit=10,
                        offset_id=42,
                        timeout=5,
                        endpoint=None,
                        env_file=None,
                        account="main",
                    )
                )

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["intent"], "list_channel_links")
