import json

from benchmark.models import (
    BenchmarkTarget,
    DownloadResult,
    load_benchmark_set,
    load_results,
    save_benchmark_set,
    save_results,
)


def test_save_and_load_benchmark_set_round_trip(tmp_path):
    path = tmp_path / "data" / "benchmark_set.json"
    targets = [
        BenchmarkTarget(
            label="big-video-1",
            chat="durov",
            message_id=123,
            link="https://t.me/durov/123",
            expected_size_bytes=52_428_800,
        )
    ]

    save_benchmark_set(path, targets)
    loaded = load_benchmark_set(path)

    assert loaded == targets
    assert json.loads(path.read_text())[0]["label"] == "big-video-1"


def test_save_and_load_results_round_trip(tmp_path):
    path = tmp_path / "data" / "results_telethon.json"
    results = [
        DownloadResult(
            label="big-video-1",
            backend="telethon",
            ok=True,
            elapsed_seconds=12.5,
            bytes_downloaded=52_428_800,
            resumed=False,
        )
    ]

    save_results(path, results)
    loaded = load_results(path)

    assert loaded == results
