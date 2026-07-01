import pytest

from benchmark.select_targets import extract_file_size, parse_link


def test_parse_link_public_username():
    chat, message_id = parse_link("https://t.me/durov/123")
    assert chat == "durov"
    assert message_id == 123


def test_parse_link_private_channel_id():
    chat, message_id = parse_link("https://t.me/c/1234567890/456")
    assert chat == "-1001234567890"
    assert message_id == 456


def test_parse_link_rejects_non_telegram_url():
    with pytest.raises(ValueError, match="not a recognized t.me post link"):
        parse_link("https://example.com/foo/1")


def test_extract_file_size_from_tg_message_envelope():
    envelope = {
        "ok": True,
        "payload": {
            "chat": {"id": 123},
            "message_id": 456,
            "message": {"id": 456, "file_size": 52428800, "media_type": "video"},
        },
    }
    assert extract_file_size(envelope) == 52428800


def test_extract_file_size_returns_none_when_no_media():
    envelope = {"ok": True, "payload": {"message": {"id": 1, "file_size": None}}}
    assert extract_file_size(envelope) is None


def test_extract_file_size_returns_none_when_message_missing():
    envelope = {"ok": True, "payload": {"message": None}}
    assert extract_file_size(envelope) is None
