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


def extract_json_envelope(stdout: str) -> dict:
    """`tg download --json` interleaves PROGRESS lines with its JSON envelope
    on stdout even with --json set; the envelope is the trailing `{...}`
    block, so parse from the first brace rather than the whole stream."""
    json_start = stdout.find("{")
    if json_start == -1:
        raise json.JSONDecodeError("no JSON object found in stdout", stdout, 0)
    return json.loads(stdout[json_start:])


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
        envelope = extract_json_envelope(proc.stdout)
    except json.JSONDecodeError:
        envelope = {"ok": False, "error": proc.stderr.strip() or "no JSON output"}

    downloaded_size = None
    payload = envelope.get("payload") if isinstance(envelope.get("payload"), dict) else {}
    downloaded_size = payload.get("size_bytes")
    local_path = payload.get("path")
    if downloaded_size is None and local_path and Path(local_path).exists():
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
