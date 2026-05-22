import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from telegram_mcp.download_cleanup import cleanup_download_dir, estimate_download_cleanup


class DownloadCleanupTests(unittest.TestCase):
    def test_cleanup_removes_only_old_top_level_files(self):
        now = 1_800_000_000.0

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old_file = root / "old.mp4"
            old_file.write_bytes(b"old")
            os.utime(old_file, (now - 8 * 24 * 60 * 60, now - 8 * 24 * 60 * 60))

            recent_file = root / "recent.mp4"
            recent_file.write_bytes(b"recent")
            os.utime(recent_file, (now - 2 * 24 * 60 * 60, now - 2 * 24 * 60 * 60))

            nested_dir = root / "nested"
            nested_dir.mkdir()
            nested_old_file = nested_dir / "old.txt"
            nested_old_file.write_text("nested", encoding="utf-8")
            os.utime(
                nested_old_file,
                (now - 8 * 24 * 60 * 60, now - 8 * 24 * 60 * 60),
            )

            symlink = root / "old-link.mp4"
            symlink.symlink_to(recent_file)

            result = cleanup_download_dir(root, retention_days=7, now=now)

            self.assertEqual(result.deleted_files, 1)
            self.assertEqual(result.deleted_bytes, 3)
            self.assertFalse(old_file.exists())
            self.assertTrue(recent_file.exists())
            self.assertTrue(nested_old_file.exists())
            self.assertTrue(symlink.exists())

    def test_non_positive_retention_disables_cleanup(self):
        now = 1_800_000_000.0

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old_file = root / "old.mp4"
            old_file.write_bytes(b"old")
            os.utime(old_file, (now - 8 * 24 * 60 * 60, now - 8 * 24 * 60 * 60))

            result = cleanup_download_dir(root, retention_days=0, now=now)

            self.assertEqual(result.deleted_files, 0)
            self.assertTrue(old_file.exists())

    def test_estimate_counts_candidates_without_deleting(self):
        now = 1_800_000_000.0

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old_file = root / "old.mp4"
            old_file.write_bytes(b"old")
            os.utime(old_file, (now - 8 * 24 * 60 * 60, now - 8 * 24 * 60 * 60))

            result = estimate_download_cleanup(root, retention_days=7, now=now)

            self.assertTrue(result.dry_run)
            self.assertEqual(result.candidate_files, 1)
            self.assertEqual(result.candidate_bytes, 3)
            self.assertEqual(result.deleted_files, 0)
            self.assertTrue(old_file.exists())

    def test_cleanup_reports_scan_errors_without_raising(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            with patch.object(Path, "iterdir", side_effect=PermissionError("nope")):
                result = cleanup_download_dir(root, retention_days=7)

            self.assertEqual(result.deleted_files, 0)
            self.assertEqual(result.candidate_files, 0)
            self.assertEqual(len(result.errors), 1)
            self.assertIn("PermissionError", result.errors[0])

    def test_cleanup_module_dry_run_json_does_not_delete(self):
        now = time.time()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old_file = root / "old.mp4"
            old_file.write_bytes(b"old")
            os.utime(old_file, (now - 8 * 24 * 60 * 60, now - 8 * 24 * 60 * 60))

            env = os.environ.copy()
            env.update(
                {
                    "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src"),
                    "TELEGRAM_API_ID": "1",
                    "TELEGRAM_API_HASH": "hash",
                    "TELEGRAM_DOWNLOAD_DIR": str(root),
                    "TELEGRAM_DOWNLOAD_RETENTION_DAYS": "7",
                }
            )
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "telegram_mcp.download_cleanup",
                    "--dry-run",
                    "--json",
                ],
                text=True,
                capture_output=True,
                env=env,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertTrue(payload["dry_run"])
            self.assertEqual(payload["candidate_files"], 1)
            self.assertEqual(payload["deleted_files"], 0)
            self.assertTrue(old_file.exists())
