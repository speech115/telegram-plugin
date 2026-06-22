from telegram_mcp.telegram_fast_tool_check import _live_argv
from telegram_mcp.telegram_metadata_scaffold import build_report


def test_metadata_scaffold_is_complete_for_current_surface():
    report = build_report()

    assert report["status"] == "ok"
    assert not report["findings"]
    assert any(item["tool_name"] == "telegram_count_videos" for item in report["tools"])


def test_fast_tool_check_maps_live_argv_without_running_live():
    assert _live_argv("telegram_count_photos", "@channel", None) == [
        "bin/tg",
        "count",
        "photos",
        "@channel",
        "--json",
    ]
    assert _live_argv("telegram_latest_message", "@channel", None) == [
        "bin/tg",
        "latest",
        "@channel",
        "--json",
    ]
