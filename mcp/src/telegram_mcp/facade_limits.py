"""Shared fast-default limits for dialog facade reads."""

from __future__ import annotations

FAST_DIALOG_READ_LIMIT = 20
FAST_CONTEXT_RECENT_LIMIT = 20
FAST_SEARCH_LIMIT = 15
FAST_MEMBER_EXPORT_LIMIT = 200

MAX_FAST_DIALOG_READ_LIMIT = 50
MAX_FULL_DIALOG_READ_LIMIT = 200
MAX_MEMBER_EXPORT_LIMIT = 500


def clamp_dialog_read_limit(
    limit: int,
    *,
    include_voice_transcription: bool,
    include_sender_name: bool = False,
) -> int:
    """Cap first-pass reads unless the caller explicitly opts into heavy modes."""
    if limit < 1:
        return 1
    if include_voice_transcription or include_sender_name:
        return min(limit, MAX_FULL_DIALOG_READ_LIMIT)
    return min(limit, MAX_FAST_DIALOG_READ_LIMIT)


def clamp_context_recent_limit(limit: int, *, mode: str) -> int:
    if limit < 1:
        return 1
    if mode.strip().lower() == "full":
        return min(limit, MAX_FULL_DIALOG_READ_LIMIT)
    return min(limit, MAX_FAST_DIALOG_READ_LIMIT)


def clamp_search_limit(limit: int) -> int:
    if limit < 1:
        return 1
    return min(limit, MAX_FAST_DIALOG_READ_LIMIT)


def clamp_member_export_limit(limit: int) -> int:
    if limit < 1:
        return 1
    return min(limit, MAX_MEMBER_EXPORT_LIMIT)