"""SQLite registry for local Telegram media downloads."""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True)
class DownloadRegistryEntry:
    chat_id: str
    chat_ref: str
    message_id: int
    local_path: str
    size: int
    sha256: str
    downloaded_at: str


class DownloadRegistry:
    def __init__(self, path: Path) -> None:
        self.path = path

    def upsert_download(
        self,
        *,
        chat_id: int | str,
        chat_ref: str,
        message_id: int,
        local_path: Path,
        downloaded_at: datetime | None = None,
    ) -> DownloadRegistryEntry:
        path = local_path.expanduser()
        stat = path.stat()
        entry = DownloadRegistryEntry(
            chat_id=str(chat_id),
            chat_ref=chat_ref,
            message_id=message_id,
            local_path=str(path),
            size=stat.st_size,
            sha256=_sha256(path),
            downloaded_at=_format_downloaded_at(downloaded_at),
        )

        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("BEGIN IMMEDIATE")
            _ensure_schema(conn)
            conn.execute(
                """
                INSERT INTO media_downloads (
                    chat_id,
                    chat_ref,
                    message_id,
                    local_path,
                    size,
                    sha256,
                    downloaded_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(chat_id, message_id) DO UPDATE SET
                    chat_ref = excluded.chat_ref,
                    local_path = excluded.local_path,
                    size = excluded.size,
                    sha256 = excluded.sha256,
                    downloaded_at = excluded.downloaded_at
                """,
                (
                    entry.chat_id,
                    entry.chat_ref,
                    entry.message_id,
                    entry.local_path,
                    entry.size,
                    entry.sha256,
                    entry.downloaded_at,
                ),
            )
            conn.commit()

        return entry

    def get(self, *, chat_id: int | str, message_id: int) -> DownloadRegistryEntry | None:
        with sqlite3.connect(self.path) as conn:
            conn.row_factory = sqlite3.Row
            _ensure_schema(conn)
            row = conn.execute(
                """
                SELECT chat_id, chat_ref, message_id, local_path, size, sha256, downloaded_at
                FROM media_downloads
                WHERE chat_id = ? AND message_id = ?
                """,
                (str(chat_id), message_id),
            ).fetchone()
        if row is None:
            return None
        return DownloadRegistryEntry(
            chat_id=row["chat_id"],
            chat_ref=row["chat_ref"],
            message_id=row["message_id"],
            local_path=row["local_path"],
            size=row["size"],
            sha256=row["sha256"],
            downloaded_at=row["downloaded_at"],
        )


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS media_downloads (
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


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _format_downloaded_at(downloaded_at: datetime | None) -> str:
    value = downloaded_at or datetime.now(UTC)
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()
