"""Tests for the tool error handler decorator."""

import asyncio
import unittest

from telegram_mcp.errors import ToolContractError, tool_error_handler


class ErrorHandlerTests(unittest.TestCase):
    def test_passes_through_normal_result(self):
        @tool_error_handler
        async def ok_tool():
            return {"ok": True}

        result = asyncio.run(ok_tool())
        self.assertEqual(result, {"ok": True})

    def test_wraps_known_telethon_error_as_value_error(self):
        from telethon.errors import ChatWriteForbiddenError

        @tool_error_handler
        async def forbidden_tool():
            raise ChatWriteForbiddenError(None)

        with self.assertRaises(ValueError) as ctx:
            asyncio.run(forbidden_tool())
        self.assertIn("permission_denied:", str(ctx.exception))

    def test_wraps_more_telegram_errors_as_friendly_value_errors(self):
        from telethon.errors import PeerFloodError, UsernameInvalidError

        @tool_error_handler
        async def peer_flood_tool():
            raise PeerFloodError(None)

        with self.assertRaises(ValueError) as ctx:
            asyncio.run(peer_flood_tool())
        self.assertIn("rate_limited:", str(ctx.exception))

        @tool_error_handler
        async def invalid_username_tool():
            raise UsernameInvalidError(None)

        with self.assertRaises(ValueError) as ctx:
            asyncio.run(invalid_username_tool())
        self.assertIn("invalid_input:", str(ctx.exception))

    def test_wraps_contract_error_as_typed_value_error(self):
        @tool_error_handler
        async def invalid_range_tool():
            raise ToolContractError("invalid_date_range", "date_from must not exceed date_to")

        with self.assertRaises(ValueError) as ctx:
            asyncio.run(invalid_range_tool())

        self.assertIn("invalid_date_range: date_from must not exceed date_to", str(ctx.exception))

    def test_flood_wait_does_not_retry_tool_body(self):
        from telethon.errors import FloodWaitError

        call_count = 0

        @tool_error_handler
        async def rate_limited_tool():
            nonlocal call_count
            call_count += 1
            exc = FloodWaitError(None)
            exc.seconds = 0
            raise exc

        with self.assertRaises(ValueError) as ctx:
            asyncio.run(rate_limited_tool())

        self.assertIn("rate_limited:", str(ctx.exception))
        self.assertEqual(call_count, 1)

    def test_flood_wait_long_raises_value_error(self):
        from telethon.errors import FloodWaitError

        @tool_error_handler
        async def slow_tool():
            exc = FloodWaitError(None)
            exc.seconds = 60
            raise exc

        with self.assertRaises(ValueError) as ctx:
            asyncio.run(slow_tool())
        self.assertIn("rate limit", str(ctx.exception))

    def test_unknown_exception_propagates(self):
        @tool_error_handler
        async def broken_tool():
            raise RuntimeError("unexpected")

        with self.assertRaises(RuntimeError):
            asyncio.run(broken_tool())

    def test_preserves_function_name(self):
        @tool_error_handler
        async def my_special_tool():
            pass

        self.assertEqual(my_special_tool.__name__, "my_special_tool")
