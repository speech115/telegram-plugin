from benchmark.compare import build_report
from benchmark.models import DownloadResult


def test_build_report_includes_table_rows_and_averages():
    telethon = [DownloadResult("big-video-1", "telethon", True, 10.0, 52428800, False)]
    tdlib = [DownloadResult("big-video-1", "tdlib", True, 8.0, 52428800, True)]

    report = build_report(telethon, tdlib)

    assert "big-video-1" in report
    assert "telethon=10.00s, tdlib=8.00s" in report
    assert "resume after interruption: True" in report


def test_build_report_handles_no_successful_runs():
    telethon = [DownloadResult("big-video-1", "telethon", False, 0.0, None, False, error="boom")]
    tdlib = [DownloadResult("big-video-1", "tdlib", False, 0.0, None, False, error="boom")]

    report = build_report(telethon, tdlib)

    assert "Not enough successful runs" in report
