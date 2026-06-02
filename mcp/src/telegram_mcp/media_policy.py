"""Default local media download locations and retention."""

from __future__ import annotations

from pathlib import Path

DEFAULT_DOWNLOAD_DIR = Path.home() / ".cache" / "telegram-mcp" / "downloads"
DEFAULT_DOWNLOAD_RETENTION_DAYS = 7
DEFAULT_SESSION_DIR = Path.home() / ".telegram-mcp"


def default_download_dir() -> Path:
    path = DEFAULT_DOWNLOAD_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path