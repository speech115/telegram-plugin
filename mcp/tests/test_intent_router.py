import unittest

from telegram_mcp.errors import ToolContractError
from telegram_mcp.intent_router import (
    assert_live_result_data_source,
    enforce_live_read_route,
    format_contract_error,
)


class IntentRouterTests(unittest.TestCase):
    def test_enforce_live_blocks_archive_hint(self) -> None:
        with self.assertRaises(ToolContractError) as ctx:
            enforce_live_read_route(
                tool_name="telegram_read",
                day="2026-06-04",
                data_source_hint="telecrawl_archive",
            )
        self.assertEqual(ctx.exception.code, "archive_route_blocked")

    def test_format_contract_error_includes_next_action(self) -> None:
        exc = ToolContractError("archive_route_blocked", "must use live")
        text = format_contract_error(exc)
        self.assertIn("next:", text)
        self.assertIn("tg read today", text)

    def test_assert_live_result_rejects_non_live_source(self) -> None:
        with self.assertRaises(ToolContractError) as ctx:
            assert_live_result_data_source(
                {"data_source": "mirror_snapshot"},
                tool_name="telegram_read",
                intent="today",
            )
        self.assertEqual(ctx.exception.code, "archive_fallback_blocked")


if __name__ == "__main__":
    unittest.main()