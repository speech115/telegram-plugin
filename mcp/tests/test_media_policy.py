import unittest
from pathlib import Path

from telegram_mcp.config import Settings
from telegram_mcp.media_policy import (
    DEFAULT_DOWNLOAD_DIR,
    DEFAULT_DOWNLOAD_RETENTION_DAYS,
    DEFAULT_SESSION_DIR,
)


class MediaPolicyTests(unittest.TestCase):
    def test_defaults_use_private_cache_paths(self) -> None:
        settings = Settings(api_id=1, api_hash="hash")
        self.assertEqual(settings.download_dir, DEFAULT_DOWNLOAD_DIR)
        self.assertEqual(settings.session_dir, DEFAULT_SESSION_DIR)
        self.assertEqual(settings.download_retention_days, DEFAULT_DOWNLOAD_RETENTION_DAYS)
        self.assertIn(".cache", str(settings.download_dir))
        self.assertTrue(
            str(settings.download_dir).startswith(str(Path.home())),
        )