import unittest

from telegram_mcp.facade_limits import (
    FAST_DIALOG_READ_LIMIT,
    clamp_dialog_read_limit,
    clamp_member_export_limit,
    clamp_search_limit,
)


class FacadeLimitTests(unittest.TestCase):
    def test_fast_read_caps_large_limit(self) -> None:
        self.assertEqual(
            clamp_dialog_read_limit(500, include_voice_transcription=False),
            50,
        )

    def test_full_read_allows_higher_cap(self) -> None:
        self.assertEqual(
            clamp_dialog_read_limit(150, include_voice_transcription=True),
            150,
        )

    def test_search_limit_is_bounded(self) -> None:
        self.assertEqual(clamp_search_limit(999), 50)

    def test_member_export_limit_is_bounded(self) -> None:
        self.assertEqual(clamp_member_export_limit(9999), 500)

    def test_fast_default_is_small(self) -> None:
        self.assertEqual(FAST_DIALOG_READ_LIMIT, 20)