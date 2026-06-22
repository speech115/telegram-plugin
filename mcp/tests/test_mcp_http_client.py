import unittest

from telegram_mcp.mcp_http_client import McpCliError, endpoint_attempts


class McpHttpClientTests(unittest.TestCase):
    def test_endpoint_attempts_default_to_main_account_only(self):
        attempts = endpoint_attempts(host="127.0.0.1")

        self.assertEqual(len(attempts), 1)
        self.assertEqual(attempts[0].port, 8799)
        self.assertIn(".telegram-mcp", attempts[0].env_file)
        self.assertNotIn(".telegram-mcp-pl", attempts[0].env_file)

    def test_endpoint_attempts_can_select_pl_account(self):
        attempts = endpoint_attempts(host="127.0.0.1", account="pl")

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

    def test_endpoint_attempts_reject_unknown_account(self):
        with self.assertRaises(McpCliError) as ctx:
            endpoint_attempts(host="127.0.0.1", account="unknown")

        self.assertIn("main", str(ctx.exception))

    def test_endpoint_attempts_allow_explicit_same_account_failover_ports(self):
        attempts = endpoint_attempts(
            host="127.0.0.1",
            account="main",
            primary_port=8799,
            failover_ports=[8798],
        )

        self.assertEqual([attempt.port for attempt in attempts], [8799, 8798])


if __name__ == "__main__":
    unittest.main()
