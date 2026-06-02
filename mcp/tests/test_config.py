import tempfile
import unittest
from pathlib import Path
from struct import pack

from telethon.sessions import StringSession

from telegram_mcp.config import Settings


class ConfigTests(unittest.TestCase):
    def test_download_retention_uses_private_cache_defaults(self):
        settings = Settings(api_id=1, api_hash="hash")

        self.assertEqual(settings.download_retention_days, 7)
        self.assertIn(".cache", str(settings.download_dir))

    def test_scheduler_and_timeout_defaults_are_safe_for_shared_daemon(self):
        settings = Settings(api_id=1, api_hash="hash")

        self.assertIsNone(settings.download_registry_path)
        self.assertEqual(settings.connect_timeout_seconds, 15.0)
        self.assertEqual(settings.mcp_probe_timeout_seconds, 15.0)
        self.assertEqual(settings.dialog_read_cache_ttl_seconds, 5)
        self.assertEqual(settings.read_inflight_dedupe_size, 128)
        self.assertEqual(settings.transcript_cache_size, 256)
        self.assertEqual(settings.tool_read_timeout_seconds, 30.0)
        self.assertEqual(settings.tool_media_timeout_seconds, 120.0)
        self.assertEqual(settings.scheduler_read_concurrency, 4)
        self.assertEqual(settings.scheduler_write_concurrency, 1)
        self.assertEqual(settings.tool_enrich_timeout_seconds, 15.0)
        self.assertEqual(settings.scheduler_enrich_concurrency, 4)
        self.assertTrue(settings.circuit_breaker_enabled)
        self.assertEqual(settings.circuit_breaker_failure_threshold, 3)
        self.assertEqual(settings.circuit_breaker_recovery_seconds, 30.0)
        self.assertEqual(settings.default_voice_transcription_budget, 3)
        self.assertEqual(settings.read_max_messages, 100)
        self.assertEqual(settings.read_max_chars, 40000)
        self.assertEqual(settings.read_max_media_items, 25)
        self.assertTrue(settings.write_audit_enabled)
        self.assertEqual(settings.write_audit_log_path.name, "write-audit.jsonl")

    def test_build_session_uses_string_session_when_configured(self):
        session_token = "1" + StringSession.encode(
            pack(">B4sH256s", 1, b"\x7f\x00\x00\x01", 443, b"\x00" * 256)
        )
        settings = Settings(
            api_id=1,
            api_hash="hash",
            session_string=session_token,
        )

        session = settings.build_session()

        self.assertIsInstance(session, StringSession)

    def test_session_dir_is_not_required_for_string_sessions(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            session_token = "1" + StringSession.encode(
                pack(">B4sH256s", 1, b"\x7f\x00\x00\x01", 443, b"\x00" * 256)
            )
            settings = Settings(
                api_id=1,
                api_hash="hash",
                session_string=session_token,
                session_dir=tmp_path / "sessions",
                download_dir=tmp_path / "downloads",
            )

            settings.ensure_dirs()

            self.assertFalse(settings.session_dir.exists())
            self.assertTrue(settings.download_dir.exists())

    def test_runtime_dirs_are_owner_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            settings = Settings(
                api_id=1,
                api_hash="hash",
                session_dir=tmp_path / "sessions",
                download_dir=tmp_path / "downloads",
            )

            settings.ensure_dirs()

            self.assertEqual(settings.session_dir.stat().st_mode & 0o777, 0o700)
            self.assertEqual(settings.download_dir.stat().st_mode & 0o777, 0o700)

    def test_custom_download_registry_dir_is_owner_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            settings = Settings(
                api_id=1,
                api_hash="hash",
                session_dir=tmp_path / "sessions",
                download_dir=tmp_path / "downloads",
                download_registry_path=tmp_path / "registry" / "media.sqlite3",
            )

            settings.ensure_dirs()

            self.assertEqual(settings.media_download_registry_path.parent.stat().st_mode & 0o777, 0o700)

    def test_download_registry_defaults_to_download_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = Settings(
                api_id=1,
                api_hash="hash",
                download_dir=root / "downloads",
            )

            self.assertEqual(
                settings.media_download_registry_path,
                root / "downloads" / "download_registry.sqlite3",
            )

            settings.ensure_dirs()

            self.assertTrue(settings.media_download_registry_path.parent.exists())

    def test_download_registry_path_can_be_configured_separately(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = Settings(
                api_id=1,
                api_hash="hash",
                download_dir=root / "downloads",
                download_registry_path=root / "registry" / "media.sqlite3",
            )

            self.assertEqual(
                settings.media_download_registry_path,
                root / "registry" / "media.sqlite3",
            )

            settings.ensure_dirs()

            self.assertTrue(settings.download_dir.exists())
            self.assertTrue(settings.media_download_registry_path.parent.exists())
