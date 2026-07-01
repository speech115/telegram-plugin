"""Benchmark media downloads through the current telegram-mcp path.

Live usage:
    uv run python benchmark/run_telethon.py

Shells out to the existing `tg download` CLI (direct Telethon, no 120s MCP
cap — see mcp/src/telegram_mcp/tg_cli.py:cmd_download) for each target in
data/benchmark_set.json, times it, and records results.
"""

import json
import subprocess
import time
from pathlib import Path

from benchmark.models import BenchmarkTarget, DownloadResult, load_benchmark_set, save_results

POC_ROOT = Path(__file__).resolve().parent.parent
TG_CLI = POC_ROOT.parent.parent / "mcp" / "bin" / "tg"
BENCHMARK_SET_PATH = POC_ROOT / "data" / "benchmark_set.json"
RESULTS_PATH = POC_ROOT / "data" / "results_telethon.json"
DOWNLOAD_DEST = POC_ROOT / "data" / "downloads" / "telethon"


def build_telethon_result(
    target: BenchmarkTarget,
    elapsed_seconds: float,
    envelope: dict,
    downloaded_size_bytes: int | None,
) -> DownloadResult:
    ok = bool(envelope.get("ok")) and downloaded_size_bytes is not None
    error = None
    if not ok:
        error = str(envelope.get("error") or envelope.get("payload") or "download failed")
    return DownloadResult(
        label=target.label,
        backend="telethon",
        ok=ok,
        elapsed_seconds=elapsed_seconds,
        bytes_downloaded=downloaded_size_bytes,
        resumed=False,
        error=error,
    )


def download_one(target: BenchmarkTarget) -> DownloadResult:
    DOWNLOAD_DEST.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    proc = subprocess.run(
        [str(TG_CLI), "download", target.link, "--dest", str(DOWNLOAD_DEST), "--account", "main", "--json"],
        capture_output=True,
        text=True,
    )
    elapsed = time.perf_counter() - started
    try:
        envelope = json.loads(proc.stdout)
    except json.JSONDecodeError:
        envelope = {"ok": False, "error": proc.stderr.strip() or "no JSON output"}

    downloaded_size = None
    payload = envelope.get("payload") if isinstance(envelope.get("payload"), dict) else {}
    local_path = payload.get("local_path") or payload.get("path")
    if local_path and Path(local_path).exists():
        downloaded_size = Path(local_path).stat().st_size

    return build_telethon_result(target, elapsed, envelope, downloaded_size)


def main() -> None:
    targets = load_benchmark_set(BENCHMARK_SET_PATH)
    results = [download_one(target) for target in targets]
    save_results(RESULTS_PATH, results)
    for result in results:
        print(f"{result.label}: ok={result.ok} elapsed={result.elapsed_seconds:.2f}s bytes={result.bytes_downloaded}")


if __name__ == "__main__":
    main()
