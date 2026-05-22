"""Advisory session locking for file-based Telethon sessions."""

from __future__ import annotations

import fcntl
import os
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
