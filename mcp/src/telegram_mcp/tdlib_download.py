"""TDLib backend for large media downloads on the `main` account only.

Graduated from the isolated POC (experiments/tdlib-media-poc/) per
mcp/docs/superpowers/specs/2026-07-01-tdlib-large-media-download-design.md.
`pytdbot` is an optional dependency (`telegram-mcp[tdlib]`) — every function
here that needs it imports it lazily, so importing this module never
requires pytdbot to be installed.
"""

from __future__ import annotations

import os
from pathlib import Path

from .locking import FileSessionLock, try_acquire_with_timeout

TELETHON_SESSION_DIR_MARKER = ".telegram-mcp"

SUPPORTED_CONTENT_KINDS = frozenset({"video", "document", "photo", "audio"})


class TdlibDownloadError(RuntimeError):
    """Raised for any TDLib download failure; callers should fall back to Telethon."""


def assert_isolated_from_telethon(files_directory: str) -> None:
    segments = Path(files_directory).parts
    if TELETHON_SESSION_DIR_MARKER in segments:
        raise ValueError(
            f"files_directory must not overlap the Telethon session tree "
            f"(found {TELETHON_SESSION_DIR_MARKER!r})"
        )


def build_client(
    api_id: int,
    api_hash: str,
    files_directory: str,
    database_encryption_key: str = "telegram-mcp-tdlib",
):
    assert_isolated_from_telethon(files_directory)
    import pytdbot

    return pytdbot.Client(
        api_id=api_id,
        api_hash=api_hash,
        files_directory=files_directory,
        database_encryption_key=database_encryption_key,
        use_file_database=True,
        use_chat_info_database=False,
        use_message_database=False,
    )


def raise_if_error(result):
    import pytdbot

    if isinstance(result, pytdbot.types.Error):
        raise TdlibDownloadError(f"TDLib error {result['code']}: {result['message']}")
    return result


def extract_file_id_from_message(message) -> int:
    content = message["content"]
    content_type = content.getType()
    if content_type == "messageVideo":
        return content["video"]["video"]["id"]
    if content_type == "messageDocument":
        return content["document"]["document"]["id"]
    if content_type == "messagePhoto":
        sizes = content["photo"]["sizes"]
        return sizes[-1]["photo"]["id"]
    if content_type == "messageAudio":
        return content["audio"]["audio"]["id"]
    raise ValueError(f"unsupported message content type for download: {content_type!r}")


def should_route_to_tdlib(
    *,
    account: str,
    tdlib_enabled: bool,
    content_kind: str | None,
    media_size_bytes: int | None,
    threshold_mb: float,
) -> bool:
    if account != "main":
        return False
    if not tdlib_enabled:
        return False
    if content_kind not in SUPPORTED_CONTENT_KINDS:
        return False
    if media_size_bytes is None:
        return False
    return media_size_bytes >= threshold_mb * 1024 * 1024


async def download_via_tdlib(*, link: str, session_dir: Path) -> Path:
    """Resolve `link` via TDLib and download it fully. Returns the local file
    path on success. Raises TdlibDownloadError on any failure (lock timeout,
    TDLib error, incomplete download) — the caller decides to fall back."""
    lock = FileSessionLock(session_dir / "download.lock")
    if not try_acquire_with_timeout(lock, timeout_seconds=5.0):
        raise TdlibDownloadError("could not acquire TDLib session lock within 5s")

    try:
        client = build_client(
            api_id=int(os.environ["TELEGRAM_API_ID"]),
            api_hash=os.environ["TELEGRAM_API_HASH"],
            files_directory=str(session_dir),
        )
        await client.start()
        try:
            link_info = raise_if_error(await client.getMessageLinkInfo(url=link))
            message = raise_if_error(
                await client.getMessage(
                    chat_id=link_info["chat_id"], message_id=link_info["message"]["id"]
                )
            )
            file_id = extract_file_id_from_message(message)
            result = raise_if_error(
                await client.downloadFile(
                    file_id=file_id, priority=1, synchronous=True, offset=0, limit=0
                )
            )
            local = result["local"]
            if not local or not bool(local["is_downloading_completed"]):
                raise TdlibDownloadError("TDLib download did not complete")
            return Path(local["path"])
        finally:
            await client.stop()
    finally:
        lock.release()
