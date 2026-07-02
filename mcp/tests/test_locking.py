import tempfile
import unittest
from pathlib import Path

from telegram_mcp.locking import FileSessionLock, SessionLockError, try_acquire_with_timeout


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


class TryAcquireWithTimeoutTests(unittest.IsolatedAsyncioTestCase):
    async def test_returns_false_when_held(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock_path = Path(tmp) / "telegram.lock"

            holder = FileSessionLock(lock_path)
            holder.acquire()
            try:
                waiter = FileSessionLock(lock_path)
                acquired = await try_acquire_with_timeout(
                    waiter, timeout_seconds=0.3, poll_interval_seconds=0.1
                )
                self.assertFalse(acquired)
            finally:
                holder.release()

    async def test_succeeds_once_free(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock_path = Path(tmp) / "telegram.lock"

            lock = FileSessionLock(lock_path)
            acquired = await try_acquire_with_timeout(lock, timeout_seconds=0.3)
            try:
                self.assertTrue(acquired)
            finally:
                lock.release()
