import sqlite3
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from telegram_mcp.client_media import MediaOperationsMixin
from telegram_mcp.config import Settings
from telegram_mcp.download_registry import DownloadRegistry


class RegistryMediaOperations(MediaOperationsMixin):
    def __init__(self, settings):
        self.settings = settings


class DownloadRegistryTests(unittest.TestCase):
    def test_upsert_records_download_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            media_path = root / "voice.oga"
            media_path.write_bytes(b"voice")
            registry = DownloadRegistry(root / "downloads.sqlite3")

            entry = registry.upsert_download(
                chat_id=11,
                chat_ref="@targetdaddy",
                message_id=7,
                local_path=media_path,
                remote_media_ref="document:1007:dc4:size5",
                downloaded_at=datetime(2026, 5, 9, 12, 0, tzinfo=UTC),
            )

            self.assertEqual(entry.chat_id, "11")
            self.assertEqual(entry.chat_ref, "@targetdaddy")
            self.assertEqual(entry.message_id, 7)
            self.assertEqual(entry.local_path, str(media_path))
            self.assertEqual(entry.remote_media_ref, "document:1007:dc4:size5")
            self.assertEqual(entry.size, 5)
            self.assertEqual(
                entry.sha256,
                "c57d7e92019708b614c90fa3685cd644f543a60153fb99ec9b67c381a245fb2a",
            )
            self.assertEqual(entry.downloaded_at, "2026-05-09T12:00:00+00:00")
            self.assertEqual(registry.get(chat_id=11, message_id=7), entry)

    def test_upsert_is_atomic_and_replaces_existing_row(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry_path = root / "nested" / "downloads.sqlite3"
            registry = DownloadRegistry(registry_path)

            first_media_path = root / "first.oga"
            first_media_path.write_bytes(b"first")
            registry.upsert_download(
                chat_id=11,
                chat_ref="@old",
                message_id=7,
                local_path=first_media_path,
                downloaded_at=datetime(2026, 5, 9, 12, 0, tzinfo=UTC),
            )

            second_media_path = root / "second.oga"
            second_media_path.write_bytes(b"second")
            entry = registry.upsert_download(
                chat_id=11,
                chat_ref="@new",
                message_id=7,
                local_path=second_media_path,
                downloaded_at=datetime(2026, 5, 9, 12, 1, tzinfo=UTC),
            )

            with sqlite3.connect(registry_path) as conn:
                rows = conn.execute("SELECT * FROM media_downloads").fetchall()

            self.assertEqual(len(rows), 1)
            self.assertEqual(entry.chat_ref, "@new")
            self.assertEqual(entry.local_path, str(second_media_path))
            self.assertEqual(entry.size, 6)
            self.assertEqual(registry.get(chat_id=11, message_id=7), entry)

    def test_failed_upsert_keeps_existing_row(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry = DownloadRegistry(root / "downloads.sqlite3")
            media_path = root / "voice.oga"
            media_path.write_bytes(b"voice")
            original = registry.upsert_download(
                chat_id=11,
                chat_ref="@targetdaddy",
                message_id=7,
                local_path=media_path,
                downloaded_at=datetime(2026, 5, 9, 12, 0, tzinfo=UTC),
            )

            with self.assertRaises(FileNotFoundError):
                registry.upsert_download(
                    chat_id=11,
                    chat_ref="@targetdaddy",
                    message_id=7,
                    local_path=root / "missing.oga",
                    downloaded_at=datetime(2026, 5, 9, 12, 1, tzinfo=UTC),
                )

            self.assertEqual(registry.get(chat_id=11, message_id=7), original)

    def test_existing_registry_without_remote_ref_is_migrated(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry_path = root / "downloads.sqlite3"
            media_path = root / "voice.oga"
            media_path.write_bytes(b"voice")
            with sqlite3.connect(registry_path) as conn:
                conn.execute(
                    """
                    CREATE TABLE media_downloads (
                        chat_id TEXT NOT NULL,
                        chat_ref TEXT NOT NULL,
                        message_id INTEGER NOT NULL,
                        local_path TEXT NOT NULL,
                        size INTEGER NOT NULL,
                        sha256 TEXT NOT NULL,
                        downloaded_at TEXT NOT NULL,
                        PRIMARY KEY (chat_id, message_id)
                    )
                    """
                )
                conn.execute(
                    """
                    INSERT INTO media_downloads (
                        chat_id, chat_ref, message_id, local_path, size, sha256, downloaded_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "11",
                        "@targetdaddy",
                        7,
                        str(media_path),
                        5,
                        "legacy-sha",
                        "2026-05-09T12:00:00+00:00",
                    ),
                )

            entry = DownloadRegistry(registry_path).get(chat_id=11, message_id=7)

            self.assertIsNotNone(entry)
            self.assertIsNone(entry.remote_media_ref)

    def test_media_operations_records_download_without_public_output_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            download_dir = root / "downloads"
            download_dir.mkdir()
            media_path = download_dir / "new.oga"
            media_path.write_bytes(b"new")
            settings = Settings(
                api_id=1,
                api_hash="hash",
                download_dir=download_dir,
            )
            operations = RegistryMediaOperations(settings)

            result = operations._media_info_for_downloaded_message(
                type("Msg", (), {"document": None, "photo": None})(),
                str(media_path),
            )
            operations._record_downloaded_message_media(
                chat_id=1,
                chat_ref="@targetdaddy",
                message_id=7,
                path=result.local_path,
                remote_media_ref="document:7:dc1:size3",
            )

            entry = DownloadRegistry(
                settings.media_download_registry_path,
            ).get(chat_id=1, message_id=7)
            self.assertIsNotNone(entry)
            self.assertEqual(entry.chat_ref, "@targetdaddy")
            self.assertEqual(entry.remote_media_ref, "document:7:dc1:size3")
            self.assertEqual(entry.local_path, str(media_path))
            self.assertEqual(entry.size, 3)
            self.assertEqual(result.local_path, str(media_path))
