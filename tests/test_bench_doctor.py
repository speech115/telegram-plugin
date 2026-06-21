from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import scripts.bench_doctor as bench_doctor

ROOT = Path(__file__).resolve().parents[1]


def test_bench_doctor_supports_dry_run_json() -> None:
    script = ROOT / "scripts" / "bench_doctor.py"

    result = subprocess.run(
        [sys.executable, str(script), "--runs", "3", "--dry-run", "--json"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=10,
        check=False,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert payload["runs"] == 3
    assert payload["command"][-2:] == ["maintenance", "--no-write-registry"]
    assert payload["p50_seconds"] >= 0
    assert payload["p95_seconds"] >= payload["p50_seconds"]


def test_bench_doctor_reports_timeout_without_traceback(monkeypatch) -> None:
    def raise_timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=["doctor"], timeout=1, output="partial", stderr="slow")

    monkeypatch.setattr(bench_doctor.subprocess, "run", raise_timeout)

    sample = bench_doctor.run_once(["doctor"], dry_run=False, timeout=1)

    assert sample["exit_code"] == 124
    assert sample["timeout"] is True
    assert "partial" in sample["stdout_tail"]
