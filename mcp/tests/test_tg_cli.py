import unittest

from telegram_mcp.tg_cli import _wrap_ok


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
