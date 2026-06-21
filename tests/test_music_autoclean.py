from __future__ import annotations

from telegram_control_plane.music_autoclean import (
    AudioMetadata,
    CodeEntity,
    DEFAULT_RUNTIME_ROOT,
    DEFAULT_STATE_DIR,
    build_report,
    candidate_jobs_in_playlist_order,
    parse_args,
    MusicMessage,
    classify_music_message,
    youtube_ids_from_message,
)


def message(
    message_id: int = 1,
    *,
    text: str = "Artist - Song",
    file_name: str | None = "random+abcDEF12345.m4a",
    thumb_count: int = 0,
    entities: tuple[CodeEntity, ...] = (),
    title: str | None = "Song",
    performer: str | None = "Artist",
    duration: int | None = 123,
    media_type: str | None = "audio",
) -> MusicMessage:
    return MusicMessage(
        message_id=message_id,
        text=text,
        media_type=media_type,
        mime_type="audio/m4a",
        file_name=file_name,
        audio=AudioMetadata(
            duration=duration,
            title=title,
            performer=performer,
            voice=False,
        ),
        thumb_count=thumb_count,
        entities=entities,
    )


def test_clean_post_requires_full_code_entity_thumbnail_and_metadata_match() -> None:
    msg = message(
        thumb_count=2,
        entities=(CodeEntity("MessageEntityCode", 0, len("Artist - Song")),),
    )

    result = classify_music_message(msg)

    assert result.action == "ignore_clean_post"


def test_clean_text_without_code_entity_is_candidate_when_youtube_provenance_exists() -> None:
    msg = message(text="Artist - Song", thumb_count=2)

    result = classify_music_message(msg)

    assert result.action == "candidate_process"
    assert result.youtube_ids == ("abcDEF12345",)


def test_arbitrary_audio_without_youtube_provenance_is_quarantined() -> None:
    msg = message(file_name="normal-upload.m4a", text="random caption")

    result = classify_music_message(msg)

    assert result.action == "quarantine"
    assert "no_youtube_provenance" in result.reasons


def test_changed_bot_caption_still_processes_with_filename_youtube_id() -> None:
    msg = message(text="bot changed its promo caption", file_name="x+MRkOSkBbjSw.m4a")

    result = classify_music_message(msg)

    assert result.action == "candidate_process"
    assert result.youtube_ids == ("MRkOSkBbjSw",)


def test_hidden_text_url_youtube_id_is_provenance() -> None:
    msg = message(
        file_name="opaque.m4a",
        entities=(
            CodeEntity(
                "MessageEntityTextUrl",
                0,
                1,
                "https://www.youtube.com/watch?v=MRkOSkBbjSw",
            ),
        ),
    )

    assert youtube_ids_from_message(msg) == ("MRkOSkBbjSw",)
    assert classify_music_message(msg).action == "candidate_process"


def test_missing_audio_metadata_quarantines_even_with_youtube_id() -> None:
    msg = message(title=None, file_name="x+MRkOSkBbjSw.m4a")

    result = classify_music_message(msg)

    assert result.action == "quarantine"
    assert "missing_title_or_performer" in result.reasons


def test_ledger_done_wins_before_reprocessing() -> None:
    msg = message(text="bot changed", file_name="x+MRkOSkBbjSw.m4a")

    result = classify_music_message(msg, ledger_status="done")

    assert result.action == "ignore_ledger"


def test_default_session_uses_runtime_copy_not_main_mcp_session() -> None:
    args = parse_args([])

    assert args.session == DEFAULT_RUNTIME_ROOT / "session" / "music_autoclean"
    assert args.state_dir == DEFAULT_STATE_DIR


def test_apply_requires_explicit_delete_gate() -> None:
    args = parse_args(["--apply"])

    import asyncio

    report = asyncio.run(build_report(args))

    assert report["status"] == "fail"
    assert "i-understand" in report["error"]


class FakeRaw:
    def __init__(self, message_id: int, *, file_name: str) -> None:
        from telethon.tl.types import DocumentAttributeAudio, DocumentAttributeFilename

        self.id = message_id
        self.message = "bot caption"
        self.audio = True
        self.media = object()
        self.entities = ()
        self.document = type(
            "Document",
            (),
            {
                "mime_type": "audio/mp4",
                "thumbs": [],
                "attributes": [
                    DocumentAttributeAudio(
                        duration=123,
                        title=f"Song {message_id}",
                        performer="Artist",
                    ),
                    DocumentAttributeFilename(file_name=file_name),
                ],
            },
        )()


class FakeLedger:
    def status_for(self, chat_id: int, message_id: int) -> str | None:
        return None


def test_candidate_jobs_are_processed_in_playlist_order() -> None:
    raw_messages = [
        FakeRaw(53, file_name="x+CCCCCCCCCCC.m4a"),
        FakeRaw(52, file_name="x+BBBBBBBBBBB.m4a"),
        FakeRaw(51, file_name="x+AAAAAAAAAAA.m4a"),
    ]

    jobs = candidate_jobs_in_playlist_order(
        raw_messages=raw_messages,
        ledger=FakeLedger(),  # type: ignore[arg-type]
        chat_id=-1003717342967,
        max_process=2,
    )

    assert [job.message.message_id for job in jobs] == [51, 52]
