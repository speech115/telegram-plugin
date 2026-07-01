"""Parse t.me links and pull file-size metadata from `tg message` output."""

import re

LINK_PATTERN = re.compile(
    r"^https?://t\.me/(?:c/(?P<internal_id>\d+)|(?P<username>[A-Za-z0-9_]+))/(?P<message_id>\d+)$"
)


def parse_link(link: str) -> tuple[str, int]:
    match = LINK_PATTERN.match(link.strip())
    if not match:
        raise ValueError(f"not a recognized t.me post link: {link!r}")
    message_id = int(match.group("message_id"))
    if match.group("internal_id"):
        chat = f"-100{match.group('internal_id')}"
    else:
        chat = match.group("username")
    return chat, message_id


def extract_file_size(tg_message_envelope: dict) -> int | None:
    payload = tg_message_envelope.get("payload") or {}
    message = payload.get("message") or {}
    return message.get("file_size")
