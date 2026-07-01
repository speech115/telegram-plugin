"""Advisory session locking for file-based Telethon sessions."""

from __future__ import annotations

import fcntl
import os
import time
from pathlib import Path
from typing import TextIO


class SessionLockError(RuntimeError):
    """Raised when another process already owns the session lock."""


class FileSessionLock:
    """Prevent multiple processes from sharing the same SQLite session file."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._handle: TextIO | None = None

    def acquire(self) -> None:
        if self._handle is not None:
            return

        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.path.open("a+", encoding="utf-8")

        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            handle.close()
            raise SessionLockError(
                f"Telegram session is already in use by another process: {self.path}"
            ) from exc

        handle.seek(0)
        handle.truncate()
        handle.write(f"{os.getpid()}\n")
        handle.flush()

        self._handle = handle

    def release(self) -> None:
        if self._handle is None:
            return

        try:
            fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
        finally:
            self._handle.close()
            self._handle = None


def try_acquire_with_timeout(
    lock: FileSessionLock,
    *,
    timeout_seconds: float = 5.0,
    poll_interval_seconds: float = 0.2,
) -> bool:
    """Retry ``lock.acquire()`` until it succeeds or ``timeout_seconds`` elapse.

    Returns True if acquired (caller owns the lock and must call release()).
    Returns False if the timeout elapsed without acquiring — the caller
    should fall back rather than treat this as an error.
    """
    deadline = time.monotonic() + timeout_seconds
    while True:
        try:
            lock.acquire()
            return True
        except SessionLockError:
            if time.monotonic() >= deadline:
                return False
            time.sleep(poll_interval_seconds)
