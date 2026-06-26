"""Human approval gate for send confirmations."""

from __future__ import annotations

import unittest
from http.client import HTTPConnection
from urllib.parse import urlencode
from unittest.mock import patch

import telegram_mcp.approval_server as approval_server
from telegram_mcp.client import TelegramWrapper
from telegram_mcp.config import Settings
from telegram_mcp.errors import ToolContractError
from telegram_mcp.send_confirmation import SendConfirmationStore, bind_confirmation_store
from tests.test_client import DummyTelegramClient, _run


class SendConfirmationTests(unittest.TestCase):
    def test_send_is_direct_when_human_approval_disabled(self):
        settings = Settings(
            api_id=1,
            api_hash="hash",
            write_approval_required=False,
            write_audit_enabled=False,
        )
        with patch("telegram_mcp.client.TelegramClient", DummyTelegramClient):
            wrapper = TelegramWrapper(settings)

        _run(wrapper.send_dialog_message(chat="@targetdaddy", text="hello"))

        self.assertEqual(len(wrapper.client.send_message_calls), 1)

    def test_confirmed_send_is_direct_when_human_approval_disabled(self):
        settings = Settings(
            api_id=1,
            api_hash="hash",
            write_approval_required=False,
            write_audit_enabled=False,
        )
        with patch("telegram_mcp.client.TelegramClient", DummyTelegramClient):
            wrapper = TelegramWrapper(settings)

        _run(
            wrapper._commit_confirmed_send(
                preview_id=None,
                confirmation_token=None,
                chat="@targetdaddy",
                text="hello",
                parse_mode="md",
                message_id=None,
            )
        )

        self.assertEqual(len(wrapper.client.send_message_calls), 1)

    def test_send_requires_human_approval_when_enabled(self):
        settings = Settings(api_id=1, api_hash="hash", write_approval_required=True)
        with patch("telegram_mcp.client.TelegramClient", DummyTelegramClient):
            wrapper = TelegramWrapper(settings)

        preview = _run(wrapper.prepare_send_message(chat="@targetdaddy", text="hello"))
        self.assertIsNotNone(preview.preview_id)
        self.assertIsNotNone(preview.human_approval_url)
        self.assertIn("token=", preview.human_approval_url or "")

        with self.assertRaises(ToolContractError) as ctx:
            _run(wrapper.send_dialog_message(**preview.send_args_preview))

        self.assertEqual(ctx.exception.code, "human_approval_required")
        self.assertEqual(wrapper.client.send_message_calls, [])

    def test_send_succeeds_after_human_approval(self):
        settings = Settings(
            api_id=1,
            api_hash="hash",
            write_approval_required=True,
            write_audit_enabled=False,
        )
        with patch("telegram_mcp.client.TelegramClient", DummyTelegramClient):
            wrapper = TelegramWrapper(settings)

        preview = _run(wrapper.prepare_send_message(chat="@targetdaddy", text="hello"))
        token = preview.confirmation_token
        assert token is not None
        assert preview.preview_id is not None
        wrapper._send_confirmation_store.approve(preview.preview_id)
        _run(
            wrapper._commit_confirmed_send(
                preview_id=preview.preview_id,
                confirmation_token=None,
                chat=None,
                text=None,
                parse_mode=None,
                message_id=None,
            )
        )
        self.assertEqual(len(wrapper.client.send_message_calls), 1)


class SendConfirmationStoreTests(unittest.TestCase):
    def test_reject_blocks_consume(self):
        store = SendConfirmationStore(ttl_seconds=60)
        payload = {"chat": "@x", "text_hash": "abc"}
        _preview_id, token, _ = store.mint(payload, preview_text="hi")
        store.reject(token)
        with self.assertRaises(ToolContractError) as ctx:
            store.consume(token, payload, approval_required=True)
        self.assertEqual(ctx.exception.code, "confirmation_rejected")

    def test_approve_by_token_then_consume_removes_token_lookup(self):
        store = SendConfirmationStore(ttl_seconds=60)
        payload = {"chat": "@x", "text_hash": "abc"}
        preview_id, token, _ = store.mint(payload, preview_text="hi")

        store.approve(token)
        store.consume(preview_id, None, approval_required=True, preview_id_only=True)

        self.assertIsNone(store.get(token))
        self.assertIsNone(store.get(preview_id))


class ApprovalServerTests(unittest.TestCase):
    def tearDown(self):
        approval_server.stop_approval_server()

    def test_rejects_non_loopback_host(self):
        with self.assertRaisesRegex(ValueError, "loopback"):
            approval_server.start_approval_server(host="0.0.0.0", port=0)

    def test_get_does_not_approve_and_post_requires_nonce(self):
        store = SendConfirmationStore(ttl_seconds=60)
        payload = {"chat": "@x", "send_tool": "send_dialog_message", "text_hash": "abc"}
        _preview_id, token, _ = store.mint(payload, preview_text="hi")
        record = store.get(token)
        assert record is not None
        bind_confirmation_store(store)
        approval_server.start_approval_server(host="127.0.0.1", port=0)
        server = approval_server._server
        assert server is not None
        port = server.server_address[1]

        conn = HTTPConnection("127.0.0.1", port)
        conn.request("GET", f"/telegram/approve?token={token}&action=approve")
        response = conn.getresponse()
        response.read()
        conn.close()
        self.assertEqual(response.status, 200)
        self.assertEqual(store.get(token).approval_state, "pending")  # type: ignore[union-attr]

        body = urlencode({"token": token, "nonce": "wrong", "action": "approve"})
        conn = HTTPConnection("127.0.0.1", port)
        conn.request("POST", "/telegram/approve", body=body, headers={"Content-Type": "application/x-www-form-urlencoded"})
        response = conn.getresponse()
        response.read()
        conn.close()
        self.assertEqual(response.status, 400)
        self.assertEqual(store.get(token).approval_state, "pending")  # type: ignore[union-attr]

        body = urlencode({"token": token, "nonce": record.one_time_nonce, "action": "approve"})
        conn = HTTPConnection("127.0.0.1", port)
        conn.request("POST", "/telegram/approve", body=body, headers={"Content-Type": "application/x-www-form-urlencoded"})
        response = conn.getresponse()
        response.read()
        conn.close()
        self.assertEqual(response.status, 200)
        self.assertEqual(store.get(token).approval_state, "approved")  # type: ignore[union-attr]


if __name__ == "__main__":
    unittest.main()
