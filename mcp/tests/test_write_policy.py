"""Intent router and live-only read policy."""

from __future__ import annotations

import unittest

from telegram_mcp.errors import ToolContractError
from telegram_mcp.intent_router import (
    assert_live_result_data_source,
    classify_read_intent,
    enforce_live_read_route,
)


class WritePolicyTests(unittest.TestCase):
    def test_classify_today(self):
        self.assertEqual(classify_read_intent(day="2026-06-02"), "today")

    def test_classify_recent_default(self):
        self.assertEqual(classify_read_intent(), "recent")

    def test_block_archive_hint_on_today(self):
        with self.assertRaises(ToolContractError) as ctx:
            enforce_live_read_route(
                tool_name="telegram_read",
                day="2026-06-02",
                data_source_hint="telecrawl_archive",
            )
        self.assertEqual(ctx.exception.code, "archive_route_blocked")

    def test_block_non_live_result(self):
        with self.assertRaises(ToolContractError) as ctx:
            assert_live_result_data_source(
                {"data_source": "mirror_snapshot"},
                tool_name="telegram_read",
                intent="today",
            )
        self.assertEqual(ctx.exception.code, "archive_fallback_blocked")


if __name__ == "__main__":
    unittest.main()