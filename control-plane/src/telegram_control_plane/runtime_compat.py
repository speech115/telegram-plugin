from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from .paths import MCP_REPO, TG_CLI
from .util import run_json, status_from_findings


PROBE_CODE = """
import json
from telethon.tl import alltlobjects, types
import telegram_mcp.__main__  # noqa: F401
aliases = {
    0xFE685355: "Channel",
    0x6917560B: "MessageReplyHeader",
    0x9815CEC8: "Message",
    0x695150D7: "MessageMediaPhoto",
    0x020B1422: "User",
    0xACA1657B: "UpdateMessagePoll",
    0xEDF164F1: "StoryItem",
}
alias_results = {
    hex(constructor_id): alltlobjects.tlobjects.get(constructor_id) is getattr(types, class_name)
    for constructor_id, class_name in aliases.items()
}
payload = {
    "package_file": telegram_mcp.__file__,
    "main_file": telegram_mcp.__main__.__file__,
    "channel_from_reader_patched": getattr(types.Channel, "_telegram_mcp_current_schema_patch", False),
    "channel_from_reader_module": types.Channel.from_reader.__func__.__module__,
    "constructor_aliases": alias_results,
    "constructor_aliases_ok": all(alias_results.values()),
}
payload["ok"] = (
    payload["channel_from_reader_patched"]
    and payload["channel_from_reader_module"] == "telegram_mcp.telethon_compat"
    and payload["constructor_aliases_ok"]
)
print(json.dumps(payload, sort_keys=True))
"""


def _python_bin() -> Path:
    candidate = MCP_REPO / ".venv/bin/python"
    return candidate if candidate.exists() else Path("python3")


def runtime_compat_probe() -> dict[str, Any]:
    payload = _run_probe_subprocess()
    payload["probe_source"] = "subprocess_import"
    return payload


def live_runtime_compat_probe() -> dict[str, Any]:
    doctor = run_json([str(TG_CLI), "doctor", "--json"], timeout=20)
    raw_payload = doctor.get("payload")
    payload = raw_payload if isinstance(raw_payload, dict) else doctor
    compat = payload.get("runtime_compat")
    if isinstance(compat, dict):
        payload = dict(compat)
        payload["probe_source"] = "live_doctor"
        payload["doctor_exit_code"] = doctor.get("exit_code")
        return payload
    if doctor.get("exit_code") not in {0, None}:
        return {
            "ok": False,
            "probe_source": "live_doctor",
            "doctor_unavailable": True,
            "doctor_exit_code": doctor.get("exit_code"),
            "doctor_stderr": doctor.get("stderr"),
        }
    return {
        "ok": False,
        "probe_source": "live_doctor",
        "missing_runtime_compat": True,
        "doctor_exit_code": doctor.get("exit_code"),
    }


def _run_probe_subprocess() -> dict[str, Any]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(MCP_REPO / "src")
    completed = subprocess.run(
        [str(_python_bin()), "-c", PROBE_CODE],
        cwd=str(MCP_REPO),
        env=env,
        text=True,
        capture_output=True,
        check=False,
        timeout=20,
    )
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        payload = {"ok": False, "stdout": completed.stdout.strip()}
    payload["exit_code"] = completed.returncode
    if completed.stderr.strip():
        payload["stderr"] = completed.stderr.strip()
    return payload


def audit_runtime_compat() -> dict[str, Any]:
    payload = live_runtime_compat_probe()
    fallback_probe: dict[str, Any] | None = None
    if payload.get("doctor_unavailable"):
        fallback_probe = runtime_compat_probe()
        payload = fallback_probe
    findings: list[dict[str, Any]] = []
    if not payload.get("ok"):
        findings.append(
            {
                "id": "runtime_compat_not_applied",
                "severity": "blocking",
                "message": "Telegram MCP runtime did not apply Telethon schema compatibility shims.",
                "details": {
                    "channel_from_reader_patched": payload.get("channel_from_reader_patched"),
                    "channel_from_reader_module": payload.get("channel_from_reader_module"),
                    "constructor_aliases_ok": payload.get("constructor_aliases_ok"),
                    "missing_runtime_compat": payload.get("missing_runtime_compat"),
                    "probe_source": payload.get("probe_source"),
                    "exit_code": payload.get("exit_code"),
                    "doctor_exit_code": payload.get("doctor_exit_code"),
                },
            }
        )
    return {
        "status": status_from_findings(findings),
        "findings": findings,
        "probe": payload,
        "fallback_probe": fallback_probe,
    }


def main(argv: list[str] | None = None) -> int:
    emit_json = bool(argv and "--json" in argv)
    report = audit_runtime_compat()
    if emit_json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"status: {report['status']}")
        for item in report["findings"]:
            print(f"- [{item['severity']}] {item['id']}: {item['message']}")
    return 1 if report["status"] == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
