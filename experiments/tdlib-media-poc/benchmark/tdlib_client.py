"""Isolated pytdbot client factory for the TDLib media-download POC.

Per control-plane/docs/adr/2026-06-21-tdlib-is-not-default-runtime.md, this
POC must never share state with the Telethon session tree that telegram-mcp
owns.
"""

import pytdbot

TELETHON_SESSION_DIR_MARKERS = (".telegram-mcp",)


def assert_isolated_from_telethon(files_directory: str) -> None:
    for marker in TELETHON_SESSION_DIR_MARKERS:
        if marker in files_directory:
            raise ValueError(
                f"files_directory must not overlap the Telethon session tree (found {marker!r})"
            )


def build_client(
    api_id: int,
    api_hash: str,
    files_directory: str,
    database_encryption_key: str = "tdlib-media-poc",
) -> pytdbot.Client:
    assert_isolated_from_telethon(files_directory)
    return pytdbot.Client(
        api_id=api_id,
        api_hash=api_hash,
        files_directory=files_directory,
        database_encryption_key=database_encryption_key,
    )
