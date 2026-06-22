import io
import json
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from telegram_mcp import contract_smoke


TOOL_NAMES = [
    "collect_dialog_context",
    "prepare_dialog_reply",
    "resolve_dialog",
    "search_dialog_messages",
    "collect_context",
    "draft_reply",
    "find_dialog",
    "prepare_reply_message",
    "prepare_send_message",
    "prepare_media_inspection_manifest",
    "read_dialog",
]


ACCOUNT_PORTS = {
    "main": 8799,
    "pl": 8800,
    "recklessou": 8801,
    "teamsyncsage": 8802,
    "vermassov": 8803,
}


class FakeAttempt:
    def __init__(self, *, account: str) -> None:
        self.port = ACCOUNT_PORTS[account]
        self.endpoint = f"http://127.0.0.1:{self.port}/mcp"
        self.env_file = f"/tmp/{account}.env"


async def fake_list_tools_with_failover(**kwargs):
    return TOOL_NAMES, 0.01, FakeAttempt(account=kwargs.get("account") or "main")


class FakeMcp:
    def __init__(self, *, bad_prepare_shape: bool = False) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.bad_prepare_shape = bad_prepare_shape
        self.doctor_count = 0

    async def call_tool(self, *, tool_name, arguments, **kwargs):
        self.calls.append((tool_name, dict(arguments)))
        attempt = FakeAttempt(account=kwargs.get("account") or "main")
        if tool_name == "resolve_dialog":
            return {
                "id": 123,
                "dialog_ref": "tg://dialog/user/123",
                "name": "Smoke Chat",
                "type": "user",
                "resolved_from": "me",
                "match_confidence": 1.0,
            }, 0.01, attempt
        if tool_name in {"collect_dialog_context", "collect_context"}:
            return {
                "chat": {"id": 123, "dialog_ref": "tg://dialog/user/123"},
                "messages": [],
                "message_count": 0,
                "collection_mode": "fast",
            }, 0.01, None
        if tool_name in {"prepare_dialog_reply", "draft_reply"}:
            payload = {
                "chat": {"id": 123},
                "context": {},
                "preview_only": False,
                "send_tool": "send_dialog_message",
                "send_args_preview": {},
            } if self.bad_prepare_shape else {
                "chat": {"id": 123},
                "goal": "contract smoke preview only",
                "context": {
                    "chat": {"id": 123},
                    "messages": [],
                    "message_count": 0,
                    "collection_mode": "fast",
                },
                "preview_only": True,
                "send_tool": "send_dialog_message",
                "send_args_preview": {},
            }
            return payload, 0.01, attempt
        if tool_name in {"search_dialog_messages", "read_dialog"}:
            return {
                "chat": {"id": 123, "dialog_ref": "tg://dialog/user/123"},
                "messages": [],
                "message_count": 0,
            }, 0.01, attempt
        if tool_name == "find_dialog":
            return {
                "id": 123,
                "dialog_ref": "tg://dialog/user/123",
                "name": "Smoke Chat",
                "type": "user",
                "resolved_from": "tg://dialog/user/123",
                "match_confidence": 1.0,
            }, 0.01, attempt
        if tool_name in {"prepare_send_message", "prepare_reply_message"}:
            return {
                "chat": {"id": 123, "dialog_ref": "tg://dialog/user/123"},
                "text": "contract smoke preview only",
                "preview_only": True,
                "send_tool": "telegram_confirmed_send",
                "send_args_preview": {"chat": "tg://dialog/user/123"},
            }, 0.01, attempt
        if tool_name == "prepare_media_inspection_manifest":
            return {
                "chat": {"id": 123, "dialog_ref": "tg://dialog/user/123"},
                "items": [],
                "media_count": 0,
                "download_tool": "download_dialog_media",
            }, 0.01, attempt
        if tool_name == "doctor_check":
            self.doctor_count += 1
            hit = 1 if self.doctor_count > 1 else 0
            return {
                "status": "ok",
                "runtime_stats": {
                    "dialog_read_cache_hit": hit,
                    "dialog_search_cache_hit": hit,
                },
            }, 0.01, attempt
        raise AssertionError(f"unexpected tool: {tool_name}")


class ContractSmokeTests(unittest.TestCase):
    def test_contract_smoke_runs_safe_mcp_calls(self):
        fake = FakeMcp()
        stdout = io.StringIO()
        with patch(
            "telegram_mcp.contract_smoke.list_tools_with_failover",
            side_effect=fake_list_tools_with_failover,
        ), patch(
            "telegram_mcp.contract_smoke.call_tool_with_failover",
            side_effect=fake.call_tool,
        ):
            with redirect_stdout(stdout):
                exit_code = contract_smoke.main(["--json"])

        self.assertEqual(exit_code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["profile"], "core")
        self.assertEqual(payload["transport"], "mcp_http_client")
        self.assertEqual(payload["dialog"], "tg://dialog/user/123")
        called_tools = [name for name, _args in fake.calls]
        self.assertIn("resolve_dialog", called_tools)
        self.assertIn("collect_dialog_context", called_tools)
        self.assertIn("prepare_dialog_reply", called_tools)
        self.assertIn("search_dialog_messages", called_tools)
        self.assertNotIn("send_dialog_message", called_tools)
        self.assertEqual(payload["endpoint_port"], 8799)
        self.assertEqual(payload["calls"][0]["endpoint_port"], 8799)

    def test_contract_smoke_accepts_owner_account_names_and_reports_port(self):
        for account, port in {
            "main": 8799,
            "recklessou": 8801,
            "teamsyncsage": 8802,
            "vermassov": 8803,
        }.items():
            with self.subTest(account=account):
                fake = FakeMcp()
                stdout = io.StringIO()
                with patch(
                    "telegram_mcp.contract_smoke.list_tools_with_failover",
                    side_effect=fake_list_tools_with_failover,
                ), patch(
                    "telegram_mcp.contract_smoke.call_tool_with_failover",
                    side_effect=fake.call_tool,
                ):
                    with redirect_stdout(stdout):
                        exit_code = contract_smoke.main(["--account", account, "--json"])

                payload = json.loads(stdout.getvalue())
                self.assertEqual(exit_code, 0)
                self.assertEqual(payload["account"], account)
                self.assertEqual(payload["endpoint_port"], port)

    def test_contract_smoke_app_media_profile_checks_readonly_aliases(self):
        fake = FakeMcp()
        stdout = io.StringIO()
        with patch(
            "telegram_mcp.contract_smoke.list_tools_with_failover",
            side_effect=fake_list_tools_with_failover,
        ), patch(
            "telegram_mcp.contract_smoke.call_tool_with_failover",
            side_effect=fake.call_tool,
        ):
            with redirect_stdout(stdout):
                exit_code = contract_smoke.main(["--profile", "app-media", "--json"])

        self.assertEqual(exit_code, 0)
        called_tools = [name for name, _args in fake.calls]
        self.assertIn("find_dialog", called_tools)
        self.assertIn("read_dialog", called_tools)
        self.assertIn("collect_context", called_tools)
        self.assertIn("draft_reply", called_tools)
        self.assertIn("prepare_send_message", called_tools)
        self.assertIn("prepare_reply_message", called_tools)
        self.assertIn("prepare_media_inspection_manifest", called_tools)
        self.assertNotIn("send_dialog_message", called_tools)

    def test_contract_smoke_cache_stats_proof_checks_hit_counters(self):
        fake = FakeMcp()
        stdout = io.StringIO()
        with patch(
            "telegram_mcp.contract_smoke.list_tools_with_failover",
            side_effect=fake_list_tools_with_failover,
        ), patch(
            "telegram_mcp.contract_smoke.call_tool_with_failover",
            side_effect=fake.call_tool,
        ):
            with redirect_stdout(stdout):
                exit_code = contract_smoke.main(["--check-cache-stats", "--json"])

        self.assertEqual(exit_code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(
            payload["cache_stats_delta"],
            {"dialog_read_cache_hit": 1, "dialog_search_cache_hit": 1},
        )

    def test_contract_smoke_rejects_non_preview_prepare_shape(self):
        fake = FakeMcp(bad_prepare_shape=True)
        stdout = io.StringIO()
        with patch(
            "telegram_mcp.contract_smoke.list_tools_with_failover",
            side_effect=fake_list_tools_with_failover,
        ), patch(
            "telegram_mcp.contract_smoke.call_tool_with_failover",
            side_effect=fake.call_tool,
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
