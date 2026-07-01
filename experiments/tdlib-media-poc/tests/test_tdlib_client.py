import pytest

from benchmark.tdlib_client import assert_isolated_from_telethon, build_client


def test_assert_isolated_from_telethon_passes_for_poc_dir(tmp_path):
    assert_isolated_from_telethon(str(tmp_path / "tdlib-media-poc" / "data" / "tdlib"))


def test_assert_isolated_from_telethon_rejects_telethon_session_dir():
    with pytest.raises(ValueError, match="Telethon session tree"):
        assert_isolated_from_telethon("/Users/sereja/.telegram-mcp/session")


def test_build_client_constructs_with_isolated_directory(tmp_path):
    client = build_client(
        api_id=1,
        api_hash="0" * 32,
        files_directory=str(tmp_path / "tdlib"),
    )
    assert client is not None
