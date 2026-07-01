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

import pytdbot
from dotenv import load_dotenv

from benchmark.models import BenchmarkTarget, DownloadResult, load_benchmark_set, save_results
from benchmark.tdlib_client import build_client
from benchmark.tdlib_message import extract_file_id_from_message

POC_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = POC_ROOT / "data" / "tdlib"
BENCHMARK_SET_PATH = POC_ROOT / "data" / "benchmark_set.json"
RESULTS_PATH = POC_ROOT / "data" / "results_tdlib.json"


def raise_if_error(result):
    if isinstance(result, pytdbot.types.Error):
        raise RuntimeError(f"TDLib error {result['code']}: {result['message']}")
    return result


def build_tdlib_result(
    target: BenchmarkTarget,
    elapsed_seconds: float,
    file_object,
    resumed: bool,
) -> DownloadResult:
    local = file_object["local"]
    ok = bool(local["is_downloading_completed"]) if local else False
    return DownloadResult(
        label=target.label,
        backend="tdlib",
        ok=ok,
        elapsed_seconds=elapsed_seconds,
        bytes_downloaded=local["downloaded_size"] if local else None,
        resumed=resumed,
        error=None if ok else "download did not complete",
    )


async def resolve_file_id(client, target: BenchmarkTarget) -> int:
    link_info = raise_if_error(await client.getMessageLinkInfo(url=target.link))
    message = raise_if_error(
        await client.getMessage(
            chat_id=link_info["chat_id"], message_id=link_info["message"]["id"]
        )
    )
    return extract_file_id_from_message(message)


async def measure_clean_download(client, file_id: int):
    """Single-shot download latency, directly comparable to the Telethon baseline."""
    started = time.perf_counter()
    result = raise_if_error(
        await client.downloadFile(file_id=file_id, priority=1, synchronous=True, offset=0, limit=0)
    )
    elapsed = time.perf_counter() - started
    return elapsed, result


async def measure_resumability(client, file_id: int) -> bool:
    """Delete the local copy, start a fresh async download, cancel it mid-flight
    while it is still partial, then confirm a second call resumes from the
    partial bytes already on disk instead of restarting from zero."""
    raise_if_error(await client.deleteFile(file_id=file_id))
    raise_if_error(
        await client.downloadFile(file_id=file_id, priority=1, synchronous=False, offset=0, limit=0)
    )
    await asyncio.sleep(2)

    partial = raise_if_error(await client.getFile(file_id=file_id))
    partial_local = partial["local"]
    partial_bytes = partial_local["downloaded_size"] if partial_local else 0

    raise_if_error(await client.cancelDownloadFile(file_id=file_id, only_if_pending=False))

    resumed_result = raise_if_error(
        await client.downloadFile(file_id=file_id, priority=1, synchronous=True, offset=0, limit=0)
    )
    resumed_local = resumed_result["local"]
    completed = bool(resumed_local["is_downloading_completed"]) if resumed_local else False
    downloaded = resumed_local["downloaded_size"] if resumed_local else 0
    grew_from_partial = downloaded >= partial_bytes

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
