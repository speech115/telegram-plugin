"""TDLib backend for large media downloads on the `main` account only.

Graduated from the isolated POC (experiments/tdlib-media-poc/) per
mcp/docs/superpowers/specs/2026-07-01-tdlib-large-media-download-design.md.
`pytdbot` is an optional dependency (`telegram-mcp[tdlib]`) — every function
here that needs it imports it lazily, so importing this module never
requires pytdbot to be installed.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import time
from pathlib import Path

from .locking import FileSessionLock, try_acquire_with_timeout

TELETHON_SESSION_DIR_MARKER = ".telegram-mcp"

SUPPORTED_CONTENT_KINDS = frozenset({"video", "document", "photo", "audio"})

DEFAULT_DB_ENCRYPTION_KEY = "telegram-mcp-tdlib"

# Max wait for the TDLib session to reach authorizationStateReady after start().
# An unauthorized/revoked session never gets there, so bound it and fall back.
LOGIN_READY_TIMEOUT_SECONDS = 15.0


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
    database_encryption_key: str | None = None,
):
    assert_isolated_from_telethon(files_directory)
    if database_encryption_key is None:
        database_encryption_key = os.environ.get(
            "TELEGRAM_TDLIB_DB_ENCRYPTION_KEY", DEFAULT_DB_ENCRYPTION_KEY
        )
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
    if content_type == "messageAnimation":
        return content["animation"]["animation"]["id"]
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


async def start_client_ready(
    client,
    *,
    timeout_seconds: float = LOGIN_READY_TIMEOUT_SECONDS,
    poll_interval_seconds: float = 0.25,
) -> None:
    """Start ``client`` and wait until it reaches authorizationStateReady.

    ``pytdbot.Client.start()`` only auto-drives login for bot-token clients; for
    a user-account client (as built here) the default ``wait_login=True`` blocks
    forever when the session is unauthorized, because the event it waits on is
    only set on authorizationStateReady. So start with ``wait_login=False`` and
    poll the state ourselves, raising ``TdlibDownloadError`` on timeout so the
    caller falls back to Telethon instead of hanging.
    """
    await client.start(wait_login=False)
    deadline = time.monotonic() + timeout_seconds
    while True:
        state = client.authorization_state
        if state == "authorizationStateReady":
            return
        if time.monotonic() >= deadline:
            raise TdlibDownloadError(
                f"TDLib session not ready (state={state!r}); "
                "run scripts/tdlib_login.py to (re)authorize"
            )
        await asyncio.sleep(poll_interval_seconds)


async def download_via_tdlib(*, link: str, session_dir: Path, dest: Path) -> Path:
    """Resolve `link` via TDLib, download it fully, copy it to `dest`, and drop
    the TDLib-side copy. Returns `dest` on success. Raises TdlibDownloadError on
    any failure (lock timeout, unauthorized session, TDLib error, incomplete
    download) — the caller decides to fall back."""
    lock = FileSessionLock(session_dir / "download.lock")
    if not await try_acquire_with_timeout(lock, timeout_seconds=5.0):
        raise TdlibDownloadError("could not acquire TDLib session lock within 5s")

    try:
        client = build_client(
            api_id=int(os.environ["TELEGRAM_API_ID"]),
            api_hash=os.environ["TELEGRAM_API_HASH"],
            files_directory=str(session_dir),
        )
        await start_client_ready(client)
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
            shutil.copy2(local["path"], dest)
            # Drop the TDLib-side copy so files_directory doesn't grow without
            # bound; resumability matters for partial files, not ones we've
            # already copied out. Best-effort — a cleanup failure isn't fatal.
            try:
                raise_if_error(await client.deleteFile(file_id=file_id))
            except Exception:  # noqa: BLE001 - cleanup is best-effort
                pass
            return dest
        finally:
            await client.stop()
    finally:
        lock.release()
