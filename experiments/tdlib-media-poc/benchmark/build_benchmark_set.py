"""Build data/benchmark_set.json from operator-supplied t.me links.

Usage:
    uv run python benchmark/build_benchmark_set.py <t.me-link> [<t.me-link> ...]

For each link this shells out to the existing `tg message` CLI (read-only)
to fetch file_size metadata, then writes the isolated benchmark set used by
both the Telethon and TDLib benchmark runners.
"""

import json
import subprocess
import sys
from pathlib import Path

from benchmark.models import BenchmarkTarget, save_benchmark_set
from benchmark.select_targets import extract_file_size, parse_link

POC_ROOT = Path(__file__).resolve().parent.parent
TG_CLI = POC_ROOT.parent.parent / "mcp" / "bin" / "tg"
OUTPUT_PATH = POC_ROOT / "data" / "benchmark_set.json"


def fetch_metadata(chat: str, message_id: int) -> dict:
    proc = subprocess.run(
        [str(TG_CLI), "message", chat, str(message_id), "--json", "--account", "main"],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(proc.stdout)


def main(links: list[str]) -> None:
    targets = []
    for index, link in enumerate(links, start=1):
        chat, message_id = parse_link(link)
        envelope = fetch_metadata(chat, message_id)
        targets.append(
            BenchmarkTarget(
                label=f"target-{index}",
                chat=chat,
                message_id=message_id,
                link=link,
                expected_size_bytes=extract_file_size(envelope),
            )
        )
    save_benchmark_set(OUTPUT_PATH, targets)
    print(f"Wrote {len(targets)} targets to {OUTPUT_PATH}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("usage: build_benchmark_set.py <t.me-link> [<t.me-link> ...]")
    main(sys.argv[1:])
