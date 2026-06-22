"""Read-only Telegram metadata tool specifications."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MetadataCountSpec:
    key: str
    tool_name: str
    cli_name: str
    label: str
    telethon_filter: str | None = None
    route_terms: tuple[str, ...] = ()


METADATA_COUNT_SPECS: tuple[MetadataCountSpec, ...] = (
    MetadataCountSpec(
        key="posts",
        tool_name="telegram_count_posts",
        cli_name="posts",
        label="visible posts/messages",
        route_terms=("post", "posts", "пост", "сообщен", "messages"),
    ),
    MetadataCountSpec(
        key="photos",
        tool_name="telegram_count_photos",
        cli_name="photos",
        label="photos",
        telethon_filter="InputMessagesFilterPhotos",
        route_terms=("photo", "photos", "фото", "картин"),
    ),
    MetadataCountSpec(
        key="videos",
        tool_name="telegram_count_videos",
        cli_name="videos",
        label="videos",
        telethon_filter="InputMessagesFilterVideo",
        route_terms=("video", "videos", "видео"),
    ),
    MetadataCountSpec(
        key="documents",
        tool_name="telegram_count_documents",
        cli_name="documents",
        label="documents/files",
        telethon_filter="InputMessagesFilterDocument",
        route_terms=("document", "documents", "file", "files", "документ", "файл"),
    ),
    MetadataCountSpec(
        key="voice",
        tool_name="telegram_count_voice",
        cli_name="voice",
        label="voice messages",
        telethon_filter="InputMessagesFilterVoice",
        route_terms=("voice", "voices", "войс", "голосов"),
    ),
    MetadataCountSpec(
        key="pinned",
        tool_name="telegram_count_pinned",
        cli_name="pinned",
        label="pinned messages",
        telethon_filter="InputMessagesFilterPinned",
        route_terms=("pinned", "закреп", "пин"),
    ),
)

COUNT_SPECS_BY_KEY = {spec.key: spec for spec in METADATA_COUNT_SPECS}
COUNT_SPECS_BY_CLI = {spec.cli_name: spec for spec in METADATA_COUNT_SPECS}
COUNT_SPECS_BY_TOOL = {spec.tool_name: spec for spec in METADATA_COUNT_SPECS}

METADATA_TOOL_NAMES = tuple(spec.tool_name for spec in METADATA_COUNT_SPECS) + (
    "telegram_latest_message",
    "telegram_dialog_metadata",
    "telegram_get_message",
)


def count_spec_for_key(key: str) -> MetadataCountSpec:
    try:
        return COUNT_SPECS_BY_KEY[key]
    except KeyError as exc:
        supported = ", ".join(sorted(COUNT_SPECS_BY_KEY))
        raise ValueError(f"unsupported metadata count kind: {key}; supported: {supported}") from exc
