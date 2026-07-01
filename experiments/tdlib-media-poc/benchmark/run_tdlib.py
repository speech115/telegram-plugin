"""Benchmark media downloads through TDLib, including a resume test.

Live usage:
    uv run python benchmark/run_tdlib.py

Requires the isolated session created by benchmark/login_tdlib.py. For each
target: resolves the t.me link via getMessageLinkInfo, fetches the Message,
extracts the file_id, downloads it, then re-runs the same download once more
after a mid-flight cancel to prove resumability.
"""

import asyncio
import os
import time
from pathlib import Path

from dotenv import load_dotenv

from benchmark.models import BenchmarkTarget, DownloadResult, load_benchmark_set, save_results
from benchmark.tdlib_client import build_client
from benchmark.tdlib_message import extract_file_id_from_message

POC_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = POC_ROOT / "data" / "tdlib"
BENCHMARK_SET_PATH = POC_ROOT / "data" / "benchmark_set.json"
RESULTS_PATH = POC_ROOT / "data" / "results_tdlib.json"


def build_tdlib_result(
    target: BenchmarkTarget,
    elapsed_seconds: float,
    file_object: dict,
    resumed: bool,
) -> DownloadResult:
    local = file_object.get("local") or {}
    ok = bool(local.get("is_downloading_completed"))
    return DownloadResult(
        label=target.label,
        backend="tdlib",
        ok=ok,
        elapsed_seconds=elapsed_seconds,
        bytes_downloaded=local.get("downloaded_size"),
        resumed=resumed,
        error=None if ok else "download did not complete",
    )


async def resolve_file_id(client, target: BenchmarkTarget) -> int:
    link_info = await client.getMessageLinkInfo(url=target.link)
    message = await client.getMessage(
        chat_id=link_info["chat_id"], message_id=link_info["message"]["id"]
    )
    return extract_file_id_from_message(message.to_dict() if hasattr(message, "to_dict") else message)


async def measure_clean_download(client, file_id: int) -> tuple[float, dict]:
    """Single-shot download latency, directly comparable to the Telethon baseline."""
    started = time.perf_counter()
    result = await client.downloadFile(file_id=file_id, priority=1, synchronous=True, offset=0, limit=0)
    elapsed = time.perf_counter() - started
    file_dict = result.to_dict() if hasattr(result, "to_dict") else result
    return elapsed, file_dict


async def measure_resumability(client, file_id: int) -> bool:
    """Delete the local copy, start a fresh async download, cancel it mid-flight
    while it is still partial, then confirm a second call resumes from the
    partial bytes already on disk instead of restarting from zero."""
    await client.deleteFile(file_id=file_id)
    await client.downloadFile(file_id=file_id, priority=1, synchronous=False, offset=0, limit=0)
    await asyncio.sleep(2)

    partial = await client.getFile(file_id=file_id)
    partial_dict = partial.to_dict() if hasattr(partial, "to_dict") else partial
    partial_bytes = (partial_dict.get("local") or {}).get("downloaded_size", 0)

    await client.cancelDownloadFile(file_id=file_id, only_if_pending=False)

    resumed_result = await client.downloadFile(file_id=file_id, priority=1, synchronous=True, offset=0, limit=0)
    resumed_dict = resumed_result.to_dict() if hasattr(resumed_result, "to_dict") else resumed_result
    resumed_local = resumed_dict.get("local") or {}
    completed = bool(resumed_local.get("is_downloading_completed"))
    grew_from_partial = resumed_local.get("downloaded_size", 0) >= partial_bytes

    return completed and partial_bytes > 0 and grew_from_partial


async def run(targets: list[BenchmarkTarget]) -> list[DownloadResult]:
    load_dotenv(POC_ROOT / ".env")
    client = build_client(
        api_id=int(os.environ["TELEGRAM_API_ID"]),
        api_hash=os.environ["TELEGRAM_API_HASH"],
        files_directory=str(DATA_DIR),
    )
    await client.start()

    results = []
    for target in targets:
        file_id = await resolve_file_id(client, target)
        elapsed, file_object = await measure_clean_download(client, file_id)
        resumed_ok = await measure_resumability(client, file_id)
        results.append(build_tdlib_result(target, elapsed, file_object, resumed=resumed_ok))

    await client.stop()
    return results


def main() -> None:
    targets = load_benchmark_set(BENCHMARK_SET_PATH)
    results = asyncio.run(run(targets))
    save_results(RESULTS_PATH, results)
    for result in results:
        print(f"{result.label}: ok={result.ok} elapsed={result.elapsed_seconds:.2f}s resumed={result.resumed}")


if __name__ == "__main__":
    main()
