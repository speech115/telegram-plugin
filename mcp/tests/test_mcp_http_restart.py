import unittest
from unittest.mock import patch

from telegram_mcp.mcp_http_restart import restart_mcp_http_daemons


class McpHttpRestartTests(unittest.TestCase):
    def test_restart_reports_success(self):
        with patch("telegram_mcp.mcp_http_restart.subprocess.run") as run:
            run.return_value.returncode = 0
            result = restart_mcp_http_daemons(
                labels=["com.sereja.telegram-mcp-http"],
                prewarm=False,
            )

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.restarted, ["com.sereja.telegram-mcp-http"])

    def test_restart_triggers_prewarm_when_enabled(self):
        with patch("telegram_mcp.mcp_http_restart.subprocess.run") as run:
            run.return_value.returncode = 0
            with patch("telegram_mcp.mcp_prewarm.prewarm_mcp_http") as prewarm:
                restart_mcp_http_daemons(labels=["com.sereja.telegram-mcp-http"], prewarm=True)
        prewarm.assert_called_once()