"""Internal message collection models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .types import MessageInfo


@dataclass
class _MessageCollectionStats:
    voice_transcription_status: str = "not_requested"
    voice_transcription_count: int = 0
    omitted_voice_count: int = 0
    pending_voice_count: int = 0
    failed_voice_count: int = 0
    sender_resolution_count: int = 0

    def finish(self, *, include_voice_transcription: bool) -> None:
        if not include_voice_transcription:
            self.voice_transcription_status = "disabled"
        elif (
            self.omitted_voice_count
            or self.pending_voice_count
            or self.failed_voice_count
        ):
            self.voice_transcription_status = "partial"
        elif self.voice_transcription_count:
            self.voice_transcription_status = "complete"
        else:
            self.voice_transcription_status = "not_applicable"


@dataclass(frozen=True)
class _FetchedMessageRecord:
    message: Any
    media_type: str | None


@dataclass(frozen=True)
class _MessageCollectionResult:
    messages: list[MessageInfo]
    has_more_before: bool
    stats: _MessageCollectionStats
    truncated: bool = False
    truncated_reason: str | None = None


@dataclass(frozen=True)
class _TranscriptionOutcome:
    text: str | None
    pending: bool

