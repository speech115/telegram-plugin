"""Fast verification for one Telegram task-shaped tool."""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path
from typing import Any

from .metadata_tools_spec import COUNT_SPECS_BY_TOOL, LIST_SPECS_BY_TOOL


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _run_step(step_id: str, argv: list[str], *, cwd: Path) -> dict[str, Any]:
    started = time.perf_counter()
    completed = subprocess.run(argv, cwd=str(cwd), text=True, capture_output=True)
    return {
        "id": step_id,
        "argv": argv,
        "exit_code": completed.returncode,
        "duration_ms": round((time.perf_counter() - started) * 1000, 3),
        "stdout_tail": completed.stdout[-4000:],
        "stderr_tail": completed.stderr[-4000:],
        "status": "ok" if completed.returncode == 0 else "fail",
    }


def _live_argv(tool: str, chat: str, message_id: int | None) -> list[str]:
    if tool in COUNT_SPECS_BY_TOOL:
        spec = COUNT_SPECS_BY_TOOL[tool]
        return ["bin/tg", "count", spec.cli_name, chat, "--json"]
    if tool in LIST_SPECS_BY_TOOL:
        spec = LIST_SPECS_BY_TOOL[tool]
        return ["bin/tg", "list", spec.list_cli_name, chat, "--limit", "5", "--json"]
    if tool == "telegram_latest_message":
        return ["bin/tg", "latest", chat, "--json"]
    if tool == "telegram_dialog_metadata":
        return ["bin/tg", "info", chat, "--json"]
    if tool == "telegram_get_message":
        if message_id is None:
            raise ValueError("--message-id is required for telegram_get_message live smoke")
        return ["bin/tg", "message", chat, str(message_id), "--json"]
    raise ValueError(f"unsupported fast live smoke tool: {tool}")


def build_report(*, tool: str, live_chat: str | None, message_id: int | None) -> dict[str, Any]:
    root = _repo_root()
    python = str(root / ".venv/bin/python")
    steps = [
        _run_step("metadata-scaffold", [python, "-m", "telegram_mcp.telegram_metadata_scaffold", "--json"], cwd=root),
        _run_step(
            "targeted-pytest",
            [
                python,
                "-m",
                "pytest",
                "tests/test_tg_cli.py",
                "tests/test_dialog_facade_tools.py",
                "tests/test_registration.py",
                "-q",
            ],
            cwd=root,
        ),
    ]
    plugin_dir = root.parent / "plugin"
    if plugin_dir.is_dir() and (root / "bin/sync-agent-docs").exists():
        steps.append(
            _run_step(
                "agent-docs-sync-check",
                [str(root / "bin/sync-agent-docs"), "--plugin-dir", str(plugin_dir), "--check", "--no-restart", "--json"],
                cwd=root,
            )
        )
    control_root = root.parent / "control-plane"
    if (control_root / "bin/telegram-feature-status").exists():
        steps.append(
            _run_step(
                "feature-status-dry-run",
                [str(control_root / "bin/telegram-feature-status"), "--json"],
                cwd=control_root,
            )
        )
    if live_chat:
        steps.append(_run_step("live-smoke", _live_argv(tool, live_chat, message_id), cwd=root))
    return {
        "status": "ok" if all(step["status"] == "ok" for step in steps) else "fail",
        "tool": tool,
        "live_chat": live_chat,
        "steps": steps,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the fast verification lane for one Telegram tool.")
    parser.add_argument("--tool", required=True, help="MCP tool name, e.g. telegram_count_posts")
    parser.add_argument("--live-chat", help="Optional live Telegram chat for one smoke check")
    parser.add_argument("--message-id", type=int, help="Message id for telegram_get_message live smoke")
    parser.add_argument("--json", action="store_true", help="Emit JSON")
    args = parser.parse_args(argv)

    try:
        report = build_report(tool=args.tool, live_chat=args.live_chat, message_id=args.message_id)
    except Exception as exc:
        report = {"status": "fail", "tool": args.tool, "error_type": type(exc).__name__, "error": str(exc)}

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"fast tool check: {report['status']}")
        for step in report.get("steps", []):
            print(f"- {step['id']}: {step['status']} ({step['duration_ms']}ms)")
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
