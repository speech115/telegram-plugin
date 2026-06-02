"""Heuristic safety checks for agent-facing Telegram workflows."""

from __future__ import annotations

import re

_AMBIGUOUS_SEND_RE = re.compile(
    r"^\s*(send|reply|напиши|отправь)\b",
    re.IGNORECASE,
)
_UNTRUSTED_INSTRUCTION_MARKERS = (
    "ignore previous instructions",
    "ignore all previous",
    "system prompt",
    "you are now",
)


def should_block_ambiguous_send(user_text: str) -> bool:
    """Block send-shaped requests that do not name a stable dialog target."""
    text = user_text.strip()
    if not _AMBIGUOUS_SEND_RE.search(text):
        return False
    if "@" in text or "tg://dialog" in text:
        return False
    if re.search(r"\b(chat|dialog|channel|group|чат|канал|групп)\b", text, re.IGNORECASE):
        return False
    return True


def message_content_is_untrusted_instruction(text: str) -> bool:
    """Treat retrieved Telegram text as quoted content, not operator instructions."""
    lowered = text.lower()
    return any(marker in lowered for marker in _UNTRUSTED_INSTRUCTION_MARKERS)


def requires_prepare_before_send(user_text: str) -> bool:
    lowered = user_text.strip().lower()
    if lowered.startswith("prepare") or lowered.startswith("draft"):
        return True
    return "подготов" in lowered or "черновик" in lowered