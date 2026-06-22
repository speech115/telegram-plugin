"""Human approval gate for send confirmations."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from telegram_mcp.client import TelegramWrapper
from telegram_mcp.config import Settings
from telegram_mcp.errors import ToolContractError
from telegram_mcp.send_confirmation import SendConfirmationStore
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


if __name__ == "__main__":
    unittest.main()
