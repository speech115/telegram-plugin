import unittest
from unittest.mock import patch

from telegram_mcp.fast_read_today import (
    EndpointAttempt,
    FastReadError,
    exception_is_tool_error,
    endpoint_attempts,
    payload_is_tool_error,
    read_with_failover,
)


class FastReadTodayTests(unittest.TestCase):
    def test_endpoint_attempts_default_to_main_account_only(self):
        attempts = endpoint_attempts(
            host="127.0.0.1",
        )

        self.assertEqual(len(attempts), 1)
        self.assertEqual(attempts[0].port, 8799)

    def test_endpoint_attempts_can_select_pl_account(self):
        attempts = endpoint_attempts(
            host="127.0.0.1",
            account="pl",
        )

        self.assertEqual(len(attempts), 1)
        self.assertEqual(attempts[0].port, 8800)
        self.assertIn(".telegram-mcp-pl", attempts[0].env_file)

    def test_endpoint_attempts_can_select_named_owner_accounts(self):
        cases = {
            "crwddy": (8799, ".telegram-mcp/launchd.env"),
            "recklessou": (8801, ".telegram-mcp-recklessou/launchd.env"),
            "teamsyncsage": (8802, ".telegram-mcp-teamsyncsage/launchd.env"),
            "vermassov": (8803, ".telegram-mcp-vermassov/launchd.env"),
        }

        for account, (port, env_file) in cases.items():
            with self.subTest(account=account):
                attempts = endpoint_attempts(host="127.0.0.1", account=account)
                self.assertEqual(len(attempts), 1)
                self.assertEqual(attempts[0].port, port)
                self.assertIn(env_file, attempts[0].env_file)

    def test_endpoint_attempts_allow_explicit_same_account_failover_ports(self):
        attempts = endpoint_attempts(
            host="127.0.0.1",
            primary_port=8799,
            failover_ports=[8798],
        )

        self.assertEqual([attempt.port for attempt in attempts], [8799, 8798])

    def test_payload_is_tool_error_detects_unknown_tool(self):
        self.assertTrue(payload_is_tool_error("Unknown tool: telegram_read"))
        self.assertTrue(payload_is_tool_error("Error executing tool telegram_read: raw failure"))
        self.assertTrue(payload_is_tool_error({"error": "Error executing tool telegram_read: raw failure"}))
        self.assertTrue(payload_is_tool_error("permission_denied: private channel | next: ask user"))
        self.assertTrue(payload_is_tool_error({"error": "rate_limited: retry later"}))
        self.assertFalse(payload_is_tool_error({"data_source": "live_telegram"}))

    def test_exception_is_tool_error_detects_nested_tool_failure(self):
        exc = FastReadError(
            "http://127.0.0.1:8799/mcp: FastReadError: "
            "MCP tool error: 'Error executing tool telegram_read: private raw bytes'"
        )

        self.assertTrue(exception_is_tool_error(exc))

    def test_read_with_failover_does_not_cross_account_by_default(self):
        attempts = [
            EndpointAttempt("http://127.0.0.1:8799/mcp", "/tmp/a.env", 8799),
        ]

        async def fake_read_once(**kwargs):
            raise ConnectionError("down")

        with patch(
            "telegram_mcp.fast_read_today.endpoint_attempts",
            return_value=attempts,
        ), patch(
            "telegram_mcp.fast_read_today.read_once",
            side_effect=fake_read_once,
        ):
            import asyncio

            with self.assertRaises(FastReadError) as ctx:
                asyncio.run(
                    read_with_failover(
                        chat="me",
                        day="2026-06-02",
                        limit=1,
                        voice=False,
                        sender_names=False,
                        timeout=5.0,
                    )
                )

        self.assertIn("8799", str(ctx.exception))
