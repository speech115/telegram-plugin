import time
import unittest
from collections import OrderedDict

from telegram_mcp.dialog_read_cache_meta import annotate_dialog_read_cache_meta
from telegram_mcp.types import DialogHandle, DialogReadResult


class _Wrapper:
    _dialog_read_cache_ttl = 30
    _result_cache = OrderedDict()


class DialogReadCacheMetaTests(unittest.TestCase):
    def test_annotates_cache_hit_age(self) -> None:
        wrapper = _Wrapper()
        chat = DialogHandle(
            dialog_ref="me",
            id=1,
            name="me",
            type="user",
            resolved_from="me",
        )
        result = DialogReadResult(chat=chat, messages=[], message_count=0)
        cache_key = "dialog_read:recent:me:1:0:False:None:False"
        wrapper._result_cache[cache_key] = (time.monotonic() - 2.5, result)

        annotated = annotate_dialog_read_cache_meta(
            wrapper,
            result,
            cache_key=cache_key,
            cache_hit=True,
        )
        self.assertTrue(annotated.result_cache_hit)
        self.assertGreaterEqual(annotated.result_cache_age_seconds or 0.0, 2.0)
        self.assertEqual(annotated.result_cache_ttl_seconds, 30)

    def test_annotates_miss_as_zero_age(self) -> None:
        wrapper = _Wrapper()
        chat = DialogHandle(
            dialog_ref="me",
            id=1,
            name="me",
            type="user",
            resolved_from="me",
        )
        result = DialogReadResult(chat=chat, messages=[], message_count=0)
        annotated = annotate_dialog_read_cache_meta(
            wrapper,
            result,
            cache_key="missing",
            cache_hit=False,
        )
        self.assertFalse(annotated.result_cache_hit)
        self.assertEqual(annotated.result_cache_age_seconds, 0.0)


if __name__ == "__main__":
    unittest.main()