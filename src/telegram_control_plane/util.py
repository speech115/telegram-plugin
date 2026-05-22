from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any


def file_sha256(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def run_json(command: list[str], *, timeout: int = 30) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            command,
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "exit_code": 124,
            "timeout": True,
            "command": command,
            "stdout": exc.stdout or "",
            "stderr": exc.stderr or "",
        }
    payload: dict[str, Any]
    try:
        parsed = json.loads(completed.stdout)
        payload = parsed if isinstance(parsed, dict) else {"value": parsed}
    except json.JSONDecodeError:
        payload = {"stdout": completed.stdout.strip()}
    payload.setdefault("ok", completed.returncode == 0)
    payload["exit_code"] = completed.returncode
    payload["command"] = command
    if completed.stderr.strip():
        payload["stderr"] = completed.stderr.strip()
    return payload


def status_from_findings(findings: list[dict[str, Any]]) -> str:
    if any(item.get("severity") == "blocking" for item in findings):
        return "fail"
    if any(item.get("severity") in {"warn", "warning"} for item in findings):
        return "warn"
    return "ok"
