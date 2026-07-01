import pytdbot
import pytest

from benchmark.tdlib_message import extract_file_id_from_message
from benchmark.run_tdlib import build_tdlib_result
from benchmark.models import BenchmarkTarget

TARGET = BenchmarkTarget(
    label="big-video-1",
    chat="durov",
    message_id=123,
    link="https://t.me/durov/123",
    expected_size_bytes=52_428_800,
)


def test_extract_file_id_from_message_video():
    message = pytdbot.types.Message(
        content=pytdbot.types.MessageVideo(
            video=pytdbot.types.Video(video=pytdbot.types.File(id=555, size=52_428_800))
        )
    )
    assert extract_file_id_from_message(message) == 555


def test_extract_file_id_from_message_document():
    message = pytdbot.types.Message(
        content=pytdbot.types.MessageDocument(
            document=pytdbot.types.Document(document=pytdbot.types.File(id=777, size=10_000_000))
        )
    )
    assert extract_file_id_from_message(message) == 777


def test_extract_file_id_from_message_unsupported_type():
    message = pytdbot.types.Message(content=pytdbot.types.MessageText())
    with pytest.raises(ValueError, match="unsupported message content type"):
        extract_file_id_from_message(message)


def test_build_tdlib_result_completed_download():
    file_object = pytdbot.types.File(
        id=555,
        size=52_428_800,
        local=pytdbot.types.LocalFile(downloaded_size=52_428_800, is_downloading_completed=True),
    )
    result = build_tdlib_result(TARGET, 8.0, file_object, resumed=True)

    assert result.ok is True
    assert result.backend == "tdlib"
    assert result.bytes_downloaded == 52_428_800
    assert result.resumed is True
    assert result.error is None


def test_build_tdlib_result_incomplete_download():
    file_object = pytdbot.types.File(
        id=555,
        size=52_428_800,
        local=pytdbot.types.LocalFile(downloaded_size=1_000_000, is_downloading_completed=False),
    )
    result = build_tdlib_result(TARGET, 3.0, file_object, resumed=False)

    assert result.ok is False
    assert result.bytes_downloaded == 1_000_000
    assert result.error == "download did not complete"
