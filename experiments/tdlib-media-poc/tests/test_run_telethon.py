from benchmark.models import BenchmarkTarget
from benchmark.run_telethon import build_telethon_result

TARGET = BenchmarkTarget(
    label="big-video-1",
    chat="durov",
    message_id=123,
    link="https://t.me/durov/123",
    expected_size_bytes=52_428_800,
)


def test_build_telethon_result_success():
    envelope = {"ok": True, "payload": {"local_path": "/tmp/foo.mp4"}}
    result = build_telethon_result(TARGET, 12.5, envelope, 52_428_800)

    assert result.ok is True
    assert result.backend == "telethon"
    assert result.elapsed_seconds == 12.5
    assert result.bytes_downloaded == 52_428_800
    assert result.resumed is False
    assert result.error is None


def test_build_telethon_result_failure_from_bad_envelope():
    envelope = {"ok": False, "error": "flood_wait"}
    result = build_telethon_result(TARGET, 3.0, envelope, None)

    assert result.ok is False
    assert result.bytes_downloaded is None
    assert result.error == "flood_wait"
