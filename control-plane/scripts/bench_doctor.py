#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_COMMAND = [
    str(ROOT / "bin" / "tgc"),
    "doctor",
    "--profile",
    "maintenance",
    "--no-write-registry",
]


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = (len(ordered) - 1) * pct
    lower = int(index)
    upper = min(lower + 1, len(ordered) - 1)
    if lower == upper:
        return ordered[lower]
    weight = index - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def run_once(command: list[str], *, dry_run: bool, timeout: int) -> dict[str, Any]:
    started = time.perf_counter()
    if dry_run:
        time.sleep(0)
        return {"seconds": time.perf_counter() - started, "exit_code": 0}
    try:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "seconds": time.perf_counter() - started,
            "exit_code": 124,
            "timeout": True,
            "stdout_tail": str(exc.output or "").splitlines()[-20:],
            "stderr_tail": str(exc.stderr or "").splitlines()[-20:],
        }
    except OSError as exc:
        return {
            "seconds": time.perf_counter() - started,
            "exit_code": 127,
            "error": str(exc),
            "stdout_tail": [],
            "stderr_tail": [str(exc)],
        }
    return {
        "seconds": time.perf_counter() - started,
        "exit_code": completed.returncode,
        "stdout_tail": completed.stdout.splitlines()[-20:],
        "stderr_tail": completed.stderr.splitlines()[-20:],
    }


def build_report(command: list[str], runs: list[dict[str, Any]], *, dry_run: bool) -> dict[str, Any]:
    seconds = [float(item["seconds"]) for item in runs]
    failures = [item for item in runs if item.get("exit_code") != 0]
    return {
        "status": "fail" if failures else "ok",
        "command": command,
        "runs": len(runs),
        "dry_run": dry_run,
        "p50_seconds": round(statistics.median(seconds), 3) if seconds else 0.0,
        "p95_seconds": round(percentile(seconds, 0.95), 3),
        "min_seconds": round(min(seconds), 3) if seconds else 0.0,
        "max_seconds": round(max(seconds), 3) if seconds else 0.0,
        "samples": [round(value, 3) for value in seconds],
        "failures": failures,
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark Telegram maintenance doctor wall time")
    parser.add_argument("--runs", type=int, default=5, help="Number of benchmark runs")
    parser.add_argument("--timeout", type=int, default=600, help="Per-run timeout in seconds")
    parser.add_argument("--dry-run", action="store_true", help="Exercise reporting without running doctor")
    parser.add_argument("--json", action="store_true", help="Emit JSON")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    if args.runs < 1:
        raise SystemExit("--runs must be >= 1")
    runs = [run_once(DEFAULT_COMMAND, dry_run=args.dry_run, timeout=args.timeout) for _ in range(args.runs)]
    report = build_report(DEFAULT_COMMAND, runs, dry_run=args.dry_run)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"status: {report['status']}")
        print(f"runs: {report['runs']}")
        print(f"p50_seconds: {report['p50_seconds']}")
        print(f"p95_seconds: {report['p95_seconds']}")
    return 1 if report["status"] == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
