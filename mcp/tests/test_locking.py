import tempfile
import unittest
from pathlib import Path

from telegram_mcp.locking import FileSessionLock, SessionLockError


class LockingTests(unittest.TestCase):
    def test_file_session_lock_rejects_second_holder(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock_path = Path(tmp) / "telegram.lock"

            first = FileSessionLock(lock_path)
            second = FileSessionLock(lock_path)

            first.acquire()
            try:
                with self.assertRaises(SessionLockError):
                    second.acquire()
            finally:
                first.release()
