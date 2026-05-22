"""Tests for TelegramWrapper result cache."""

import asyncio
import time
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from telegram_mcp.client import TelegramWrapper
from telegram_mcp.types import UserInfo


class CacheTests(unittest.TestCase):
    def _make_wrapper(
        self,
        cache_ttl: int = 60,
        *,
        include_diagnostics: bool = False,
    ) -> TelegramWrapper:
        settings = MagicMock()
        settings.api_id = 123
        settings.api_hash = "abc"
        settings.build_session.return_value = ":memory:"
        settings.resolve_cache_size = 256
        settings.result_cache_size = 2
        settings.cache_ttl = cache_ttl
        settings.dialog_read_cache_ttl_seconds = 5
        settings.read_inflight_dedupe_size = 128
        settings.transcript_cache_size = 256
        settings.mcp_include_diagnostics = include_diagnostics
        with patch("telegram_mcp.client.TelegramClient"):
            return TelegramWrapper(settings)

    def test_cache_get_returns_none_when_empty(self):
        w = self._make_wrapper()
        self.assertIsNone(w._cache_get("anything"))

    def test_cache_set_and_get(self):
        w = self._make_wrapper()
        w._cache_set("key", "value")
        self.assertEqual(w._cache_get("key"), "value")

    def test_cache_expires_after_ttl(self):
        w = self._make_wrapper(cache_ttl=1)
        w._cache_set("key", "value")
        self.assertEqual(w._cache_get("key"), "value")
        # Simulate time passing
        w._result_cache["key"] = (time.monotonic() - 2, "value")
        self.assertIsNone(w._cache_get("key"))

    def test_cache_disabled_when_ttl_zero(self):
        w = self._make_wrapper(cache_ttl=0)
        w._cache_set("key", "value")
        self.assertIsNone(w._cache_get("key"))

    def test_invalidate_cache_by_prefix(self):
        w = self._make_wrapper()
        w._cache_set("list_chats:50:None:False:False", "chats1")
        w._cache_set("list_chats:100:None:False:False", "chats2")
        w._cache_set("list_contacts", "contacts")
        w.invalidate_cache("list_chats")
        self.assertIsNone(w._cache_get("list_chats:50:None:False:False"))
        self.assertIsNone(w._cache_get("list_chats:100:None:False:False"))
        self.assertEqual(w._cache_get("list_contacts"), "contacts")

    def test_invalidate_cache_all(self):
        w = self._make_wrapper()
        w._cache_set("a", 1)
        w._cache_set("b", 2)
        w.invalidate_cache()
        self.assertIsNone(w._cache_get("a"))
        self.assertIsNone(w._cache_get("b"))

    def test_result_cache_uses_bounded_lru_policy(self):
        w = self._make_wrapper()
        w._cache_set("a", 1)
        w._cache_set("b", 2)
        self.assertEqual(w._cache_get("a"), 1)  # touch "a", so "b" becomes oldest
        w._cache_set("c", 3)

        self.assertEqual(w._cache_get("a"), 1)
        self.assertIsNone(w._cache_get("b"))
        self.assertEqual(w._cache_get("c"), 3)

    def test_cache_emits_hit_and_miss_diagnostics_when_enabled(self):
        with patch("telegram_mcp.client.log") as log:
            w = self._make_wrapper(include_diagnostics=True)
            w._cache_set("list_chats:50:None:False:False", "value")

            self.assertEqual(w._cache_get("list_chats:50:None:False:False"), "value")
            self.assertIsNone(w._cache_get("missing"))

        events = [call.args[0] for call in log.info.call_args_list]
        self.assertIn("telegram_result_cache_store", events)
        self.assertIn("telegram_result_cache_hit", events)
        self.assertIn("telegram_result_cache_miss", events)

    def test_get_me_uses_cache(self):
        w = self._make_wrapper()
        me_mock = MagicMock()
        me_mock.id = 123
        me_mock.first_name = "Test"
        me_mock.last_name = None
        me_mock.username = "test"
        me_mock.phone = "+1234"
        me_mock.bot = False
        w.client.get_me = AsyncMock(return_value=me_mock)

        # First call — hits API
        result1 = asyncio.run(w.get_me())
        self.assertEqual(result1.id, 123)
        self.assertEqual(w.client.get_me.call_count, 1)

        # Second call — from cache
        result2 = asyncio.run(w.get_me())
        self.assertEqual(result2.id, 123)
        self.assertEqual(w.client.get_me.call_count, 1)  # no additional call

    def test_dialog_read_cache_uses_short_ttl(self):
        w = self._make_wrapper(cache_ttl=60)
        w._dialog_read_cache_set("dialog_read:key", "value")
        self.assertEqual(w._dialog_read_cache_get("dialog_read:key"), "value")

        w._result_cache["dialog_read:key"] = (time.monotonic() - 6, "value")

        self.assertIsNone(w._dialog_read_cache_get("dialog_read:key"))

    def test_dialog_cache_access_updates_runtime_stats(self):
        w = self._make_wrapper(cache_ttl=60)
        w._dialog_read_cache_set("dialog_read:key", "value")
        self.assertEqual(w._dialog_read_cache_get("dialog_read:key"), "value")
        self.assertIsNone(w._dialog_read_cache_get("dialog_read:missing"))
        w._dialog_read_cache_set("dialog_search:key", "value")
        self.assertEqual(w._dialog_read_cache_get("dialog_search:key"), "value")
        self.assertIsNone(w._dialog_read_cache_get("dialog_search:missing"))

        self.assertEqual(w._runtime_stats["dialog_read_cache_hit"], 1)
        self.assertEqual(w._runtime_stats["dialog_read_cache_miss"], 1)
        self.assertEqual(w._runtime_stats["dialog_search_cache_hit"], 1)
        self.assertEqual(w._runtime_stats["dialog_search_cache_miss"], 1)
        snapshot = w._runtime_stats_snapshot()
        self.assertEqual(snapshot["dialog_read_cache_hit_rate"], 0.5)
        self.assertEqual(snapshot["dialog_search_cache_hit_rate"], 0.5)

    def test_cache_key_normalization_is_conservative(self):
        w = self._make_wrapper()

        self.assertEqual(
            w._make_result_cache_key("dialog_read", " @Example_User ", 5),
            w._make_result_cache_key("dialog_read", "@example_user", 5),
        )
        self.assertNotEqual(
            w._make_result_cache_key("dialog_read", " Project Chat ", 5),
            w._make_result_cache_key("dialog_read", "project chat", 5),
        )
