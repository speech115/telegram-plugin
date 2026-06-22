from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .paths import CONTROL_ROOT, MCP_REPO


@dataclass(frozen=True)
class RegressionStep:
    id: str
    cwd: str
    command: tuple[str, ...]
    live: bool = False


DEFAULT_STEPS: tuple[RegressionStep, ...] = (
    RegressionStep("control-plane-tests", str(CONTROL_ROOT), ("python3", "-m", "pytest", "-q")),
    RegressionStep(
        "runtime-tests",
        str(MCP_REPO),
        ("bash", "-lc", "PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v"),
    ),
    RegressionStep(
        "restart-mcp-daemons",
        str(MCP_REPO),
        (
            "bash",
            "-lc",
            "PYTHONPATH=src .venv/bin/python - <<'PY'\n"
            "from telegram_mcp.mcp_http_restart import restart_mcp_http_daemons\n"
            "labels = [\n"
            "  'com.sereja.telegram-mcp-http',\n"
            "  'com.sereja.telegram-mcp-http-pl',\n"
            "  'com.sereja.telegram-mcp-http-recklessou',\n"
            "  'com.sereja.telegram-mcp-http-teamsyncsage',\n"
            "  'com.sereja.telegram-mcp-http-vermassov',\n"
            "]\n"
            "result = restart_mcp_http_daemons(labels=labels, prewarm=True)\n"
            "raise SystemExit(0 if result.status == 'ok' else 1)\n"
            "PY",
        ),
        True,
    ),
    RegressionStep("golden-live-smoke", str(CONTROL_ROOT), ("./bin/telegram-golden-read-smoke", "--json"), True),
    RegressionStep(
        "maintenance-doctor",
        str(CONTROL_ROOT),
        ("./bin/telegram-maintenance-doctor", "--json", "--no-write-registry"),
        True,
    ),
    RegressionStep("feature-status-dry-run", str(CONTROL_ROOT), ("./bin/telegram-feature-status", "--json"), True),
)


def _json_gate_status(step: RegressionStep, output: str, current_status: str) -> tuple[str, str | None]:
    if current_status == "fail":
        return current_status, None
    if step.id not in {"golden-live-smoke", "maintenance-doctor", "feature-status-dry-run"}:
        return current_status, None
    try:
        payload = json.loads(output)
    except json.JSONDecodeError:
        return "fail", "json_parse_failed"
    if step.id in {"golden-live-smoke", "maintenance-doctor"} and payload.get("status") != "ok":
        return "fail", f"json_status={payload.get('status')}"
    if step.id == "feature-status-dry-run" and payload.get("changed_count") != 0:
        return "fail", f"changed_count={payload.get('changed_count')}"
    return "ok", None


def _run_step_with_env(step: RegressionStep, *, timeout: int, env: dict[str, str]) -> dict[str, Any]:
    started = time.monotonic()
    completed = subprocess.run(
        step.command,
        cwd=step.cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
        check=False,
    )
    elapsed = round(time.monotonic() - started, 3)
    output = completed.stdout or ""
    status, failure_reason = _json_gate_status(step, output, "ok" if completed.returncode == 0 else "fail")
    result = {
        **asdict(step),
        "command": list(step.command),
        "exit_code": completed.returncode,
        "elapsed_seconds": elapsed,
        "status": status,
        "output_tail": output[-4000:],
    }
    if failure_reason:
        result["failure_reason"] = failure_reason
    return result


def _run_step(step: RegressionStep, *, timeout: int) -> dict[str, Any]:
    env = os.environ.copy()
    if step.id != "runtime-tests":
        return _run_step_with_env(step, timeout=timeout, env=env)
    with tempfile.TemporaryDirectory(prefix="telegram-regression-telemetry-") as tmp:
        root = Path(tmp)
        env.update(
            {
                "TELEGRAM_TELEMETRY_LOG_DIR": str(root / "telemetry"),
                "TELEGRAM_TELEMETRY_LOG_PATH": str(root / "telemetry.jsonl"),
                "TELEGRAM_TELEMETRY_STATS_PATH": str(root / "telemetry-stats.json"),
            }
        )
        return _run_step_with_env(step, timeout=timeout, env=env)


def run_regression_loop(*, include_live: bool, timeout: int) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for step in DEFAULT_STEPS:
        if step.live and not include_live:
            results.append({**asdict(step), "command": list(step.command), "status": "skipped", "reason": "live checks disabled"})
            continue
        result = _run_step(step, timeout=timeout)
        results.append(result)
        if result["status"] == "fail":
            break
    status = "ok" if all(item.get("status") in {"ok", "skipped"} for item in results) else "fail"
    return {"status": status, "include_live": include_live, "steps": results}


def render_regression_loop(report: dict[str, Any]) -> str:
    lines = [f"Telegram regression loop: {report.get('status')}"]
    for item in report.get("steps", []):
        if not isinstance(item, dict):
            continue
        lines.append(f"- {item.get('id')}: {item.get('status')} ({item.get('elapsed_seconds', '-')}s)")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Telegram regression gates in the safe sequential order.")
    parser.add_argument("--json", action="store_true", help="Emit JSON")
    parser.add_argument("--include-live", action="store_true", help="Restart daemons and run live smoke/doctor gates")
    parser.add_argument("--timeout", type=int, default=120, help="Timeout per step in seconds")
    args = parser.parse_args(argv)

    report = run_regression_loop(include_live=args.include_live, timeout=args.timeout)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(render_regression_loop(report))
    return 0 if report.get("status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
