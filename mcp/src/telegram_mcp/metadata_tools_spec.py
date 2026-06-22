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
    list_tool_name: str | None = None
    list_cli_name: str | None = None


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
    MetadataCountSpec(
        key="gifs",
        tool_name="telegram_count_gifs",
        cli_name="gifs",
        label="GIF messages",
        telethon_filter="InputMessagesFilterGif",
        route_terms=("gif", "gifs", "гиф", "гифк"),
        list_tool_name="telegram_list_gifs",
        list_cli_name="gifs",
    ),
    MetadataCountSpec(
        key="music",
        tool_name="telegram_count_music",
        cli_name="music",
        label="music/audio messages",
        telethon_filter="InputMessagesFilterMusic",
        route_terms=("music", "audio", "song", "songs", "музык", "аудио", "песн"),
        list_tool_name="telegram_list_music",
        list_cli_name="music",
    ),
    MetadataCountSpec(
        key="links",
        tool_name="telegram_count_links",
        cli_name="links",
        label="messages with links",
        telethon_filter="InputMessagesFilterUrl",
        route_terms=("link", "links", "url", "urls", "ссылк"),
        list_tool_name="telegram_list_links",
        list_cli_name="links",
    ),
    MetadataCountSpec(
        key="polls",
        tool_name="telegram_count_polls",
        cli_name="polls",
        label="poll messages",
        telethon_filter="InputMessagesFilterPoll",
        route_terms=("poll", "polls", "опрос", "голосован"),
        list_tool_name="telegram_list_polls",
        list_cli_name="polls",
    ),
    MetadataCountSpec(
        key="geo",
        tool_name="telegram_count_geo",
        cli_name="geo",
        label="geo/location messages",
        telethon_filter="InputMessagesFilterGeo",
        route_terms=("geo", "location", "locations", "гео", "локац"),
        list_tool_name="telegram_list_geo",
        list_cli_name="geo",
    ),
    MetadataCountSpec(
        key="round_video",
        tool_name="telegram_count_round_video",
        cli_name="round-video",
        label="round video messages",
        telethon_filter="InputMessagesFilterRoundVideo",
        route_terms=("round video", "round-video", "кружоч", "видеокруж"),
    ),
    MetadataCountSpec(
        key="round_voice",
        tool_name="telegram_count_round_voice",
        cli_name="round-voice",
        label="round voice messages",
        telethon_filter="InputMessagesFilterRoundVoice",
        route_terms=("round voice", "round-voice"),
    ),
    MetadataCountSpec(
        key="chat_photos",
        tool_name="telegram_count_chat_photos",
        cli_name="chat-photos",
        label="chat photo messages",
        telethon_filter="InputMessagesFilterChatPhotos",
        route_terms=("chat photo", "chat photos", "аватар", "фото чата"),
    ),
    MetadataCountSpec(
        key="mentions",
        tool_name="telegram_count_mentions",
        cli_name="mentions",
        label="mention messages",
        telethon_filter="InputMessagesFilterMyMentions",
        route_terms=("mention", "mentions", "упоминан"),
    ),
)

COUNT_SPECS_BY_KEY = {spec.key: spec for spec in METADATA_COUNT_SPECS}
COUNT_SPECS_BY_CLI = {spec.cli_name: spec for spec in METADATA_COUNT_SPECS}
COUNT_SPECS_BY_TOOL = {spec.tool_name: spec for spec in METADATA_COUNT_SPECS}
METADATA_LIST_SPECS = tuple(spec for spec in METADATA_COUNT_SPECS if spec.list_tool_name and spec.list_cli_name)
LIST_SPECS_BY_CLI = {spec.list_cli_name: spec for spec in METADATA_LIST_SPECS if spec.list_cli_name}
LIST_SPECS_BY_TOOL = {spec.list_tool_name: spec for spec in METADATA_LIST_SPECS if spec.list_tool_name}

METADATA_TOOL_NAMES = tuple(spec.tool_name for spec in METADATA_COUNT_SPECS) + (
    *(spec.list_tool_name for spec in METADATA_LIST_SPECS if spec.list_tool_name),
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
