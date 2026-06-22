"""Metadata tool scaffold/check helper.

This intentionally keeps generation narrow: read-only Telegram metadata tools
that use bounded metadata requests, not history exports or writes.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .metadata_tools_spec import METADATA_COUNT_SPECS, METADATA_TOOL_NAMES


CHECKED_FILES = (
    "src/telegram_mcp/metadata_tools_spec.py",
    "src/telegram_mcp/client_message_reads.py",
    "src/telegram_mcp/tools/dialog_facade_tools.py",
    "src/telegram_mcp/tools/__init__.py",
    "src/telegram_mcp/tg_cli.py",
    "tests/test_tg_cli.py",
    "tests/test_dialog_facade_tools.py",
    "tests/test_registration.py",
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def build_report() -> dict[str, Any]:
    root = _repo_root()
    files = {name: _read(root / name) for name in CHECKED_FILES if (root / name).exists()}
    findings: list[dict[str, str]] = []

    for tool_name in METADATA_TOOL_NAMES:
        if tool_name not in files.get("src/telegram_mcp/tools/dialog_facade_tools.py", ""):
            findings.append({"id": "missing_facade_tool", "tool": tool_name})
        if tool_name not in files.get("src/telegram_mcp/tools/__init__.py", ""):
            findings.append({"id": "missing_registration_export", "tool": tool_name})
        if tool_name not in files.get("tests/test_registration.py", ""):
            findings.append({"id": "missing_registration_test", "tool": tool_name})

    for spec in METADATA_COUNT_SPECS:
        if "METADATA_COUNT_SPECS" not in files.get("src/telegram_mcp/tg_cli.py", ""):
            findings.append({"id": "missing_cli_spec_loop", "tool": spec.tool_name})
        if "COUNT_SPECS_BY_CLI" not in files.get("tests/test_tg_cli.py", ""):
            findings.append({"id": "missing_cli_spec_test", "tool": spec.tool_name})

    return {
        "status": "ok" if not findings else "fail",
        "scope": "read_only_metadata_tools",
        "tools": [
            {
                "key": spec.key,
                "tool_name": spec.tool_name,
                "cli": f"tg count {spec.cli_name} <chat> --json",
                "filter": spec.telethon_filter,
            }
            for spec in METADATA_COUNT_SPECS
        ]
        + [
            {"key": "latest", "tool_name": "telegram_latest_message", "cli": "tg latest <chat> --json"},
            {"key": "info", "tool_name": "telegram_dialog_metadata", "cli": "tg info <chat> --json"},
            {"key": "message", "tool_name": "telegram_get_message", "cli": "tg message <chat> <message_id> --json"},
        ],
        "checked_files": list(CHECKED_FILES),
        "fast_check": "bin/telegram-fast-tool-check --tool telegram_count_posts --json",
        "findings": findings,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check the read-only Telegram metadata tool scaffold.")
    parser.add_argument("--json", action="store_true", help="Emit JSON")
    args = parser.parse_args(argv)

    report = build_report()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"metadata scaffold: {report['status']}")
        for tool in report["tools"]:
            print(f"- {tool['tool_name']}: {tool['cli']}")
        for finding in report["findings"]:
            print(f"! {finding['id']}: {finding.get('tool')}")
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
