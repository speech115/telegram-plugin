"""Data models for the TDLib vs Telethon media-download benchmark."""

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class BenchmarkTarget:
    label: str
    chat: str
    message_id: int
    link: str
    expected_size_bytes: int | None


@dataclass(frozen=True)
class DownloadResult:
    label: str
    backend: str  # "telethon" or "tdlib"
    ok: bool
    elapsed_seconds: float
    bytes_downloaded: int | None
    resumed: bool
    error: str | None = None


def load_benchmark_set(path: Path) -> list[BenchmarkTarget]:
    raw = json.loads(path.read_text())
    return [BenchmarkTarget(**item) for item in raw]


def save_benchmark_set(path: Path, targets: list[BenchmarkTarget]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([asdict(t) for t in targets], indent=2))


def load_results(path: Path) -> list[DownloadResult]:
    raw = json.loads(path.read_text())
    return [DownloadResult(**item) for item in raw]


def save_results(path: Path, results: list[DownloadResult]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([asdict(r) for r in results], indent=2))
