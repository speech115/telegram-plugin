from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from .paths import CONTROL_ROOT, POLICY_DIR, TG_CLI
from .util import load_json, status_from_findings

GOLDEN_DIALOGS_PATH = POLICY_DIR / "golden-dialogs.json"
LIVE_DATA_SOURCE = "live_telegram"


def load_golden_dialog_manifest(path: Path = GOLDEN_DIALOGS_PATH) -> dict[str, Any]:
    payload = load_json(path) or {}
    dialogs = payload.get("dialogs")
    if not isinstance(dialogs, list) or not dialogs:
        raise ValueError(f"Invalid golden dialog manifest: {path}")
    return payload


def list_golden_dialogs(*, manifest: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    data = manifest if manifest is not None else load_golden_dialog_manifest()
    dialogs: list[dict[str, Any]] = []
    for item in data.get("dialogs", []):
        if not isinstance(item, dict):
            continue
        chat = item.get("chat")
        dialog_id = item.get("id")
        if not isinstance(chat, str) or not chat.strip():
            continue
        if not isinstance(dialog_id, str) or not dialog_id.strip():
            continue
        dialogs.append(item)
    return dialogs


def read_argv(*, chat: str, limit: int) -> list[str]:
    """Prefer kit-resolved tg_cli over a stale tg on PATH."""
    tg_path = Path(TG_CLI)
    if tg_path.is_file() and tg_path.stat().st_mode & 0o111:
        command = str(tg_path)
    else:
        command = shutil.which("tg") or str(tg_path)
    return [command, "read", "today", chat, "--limit", str(limit), "--json"]


def extract_data_source(envelope: dict[str, Any]) -> str | None:
    top = envelope.get("data_source")
    if isinstance(top, str) and top.strip():
        return top.strip()
    payload = envelope.get("payload")
    if isinstance(payload, dict):
        nested = payload.get("data_source")
        if isinstance(nested, str) and nested.strip():
            return nested.strip()
    return None


def validate_read_envelope(envelope: object) -> tuple[bool, str, str | None]:
    if not isinstance(envelope, dict):
        return False, "response is not a JSON object", None
    if not envelope.get("ok"):
        error = envelope.get("error") or envelope.get("message") or "read returned ok=false"
        return False, str(error), None
    source = extract_data_source(envelope)
    if source != LIVE_DATA_SOURCE:
        return False, f"expected data_source={LIVE_DATA_SOURCE!r}, got {source!r}", source
    return True, "passed", source


def run_dialog_read(
    dialog: dict[str, Any],
    *,
    limit: int,
    timeout: float,
) -> dict[str, Any]:
    chat = str(dialog["chat"])
    argv = read_argv(chat=chat, limit=limit)
    completed = subprocess.run(
        argv,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    result: dict[str, Any] = {
        "id": dialog.get("id"),
        "chat": chat,
        "title": dialog.get("title"),
        "argv": argv,
        "exit_code": completed.returncode,
    }
    if completed.returncode != 0:
        result["status"] = "fail"
        result["message"] = (completed.stderr or completed.stdout or "non-zero exit").strip()
        return result

    try:
        envelope = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        result["status"] = "fail"
        result["message"] = f"invalid JSON: {exc}"
        return result

    ok, message, source = validate_read_envelope(envelope)
    result["status"] = "ok" if ok else "fail"
    result["message"] = message
    result["data_source"] = source
    elapsed = envelope.get("elapsed_seconds") if isinstance(envelope, dict) else None
    if isinstance(elapsed, (int, float)):
        result["elapsed_seconds"] = elapsed
    return result


def run_golden_read_smoke(
    *,
    limit: int = 1,
    timeout: float = 25.0,
    dialog_ids: list[str] | None = None,
    skip_live: bool = False,
    manifest_path: Path = GOLDEN_DIALOGS_PATH,
) -> dict[str, Any]:
    manifest = load_golden_dialog_manifest(manifest_path)
    dialogs = list_golden_dialogs(manifest=manifest)
    if dialog_ids:
        allowed = {item.strip() for item in dialog_ids if item.strip()}
        dialogs = [item for item in dialogs if str(item.get("id")) in allowed]

    if skip_live:
        return {
            "status": "ok",
            "findings": [],
            "skipped": True,
            "manifest_path": str(manifest_path),
            "dialogs": [{"id": item.get("id"), "chat": item.get("chat"), "status": "skipped"} for item in dialogs],
        }

    results: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    for dialog in dialogs:
        outcome = run_dialog_read(dialog, limit=limit, timeout=timeout)
        results.append(outcome)
        if outcome.get("status") != "ok":
            findings.append(
                {
                    "id": "golden_read_failed",
                    "severity": "blocking",
                    "message": (
                        f"Golden read failed for {outcome.get('id')!r} "
                        f"({outcome.get('chat')}): {outcome.get('message')}"
                    ),
                    "dialog": outcome.get("id"),
                    "chat": outcome.get("chat"),
                }
            )

    return {
        "status": status_from_findings(findings),
        "findings": findings,
        "skipped": False,
        "manifest_path": str(manifest_path),
        "limit": limit,
        "dialogs": results,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Live golden-dialog read smoke (tg read today).")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--limit", type=int, default=1, help="Per-dialog message limit (default 1).")
    parser.add_argument("--timeout", type=float, default=25.0, help="Per-dialog subprocess timeout.")
    parser.add_argument(
        "--dialog",
        action="append",
        dest="dialog_ids",
        metavar="ID",
        help="Run only these manifest dialog ids (repeatable).",
    )
    parser.add_argument(
        "--skip-live",
        action="store_true",
        help="Validate manifest only; do not call Telegram.",
    )
    parser.add_argument(
        "--manifest",
        default=str(GOLDEN_DIALOGS_PATH),
        help="Path to golden-dialogs.json",
    )
    args = parser.parse_args(argv)

    skip_live = args.skip_live or os.environ.get("TELEGRAM_GOLDEN_READ_SKIP", "").strip() in {
        "1",
        "true",
        "yes",
    }
    report = run_golden_read_smoke(
        limit=args.limit,
        timeout=args.timeout,
        dialog_ids=args.dialog_ids,
        skip_live=skip_live,
        manifest_path=Path(args.manifest),
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        for row in report.get("dialogs", []):
            if not isinstance(row, dict):
                continue
            label = row.get("id", "?")
            if row.get("status") == "ok":
                print(f"golden-read: {label} ok")
            elif row.get("status") == "skipped":
                print(f"golden-read: {label} skipped")
            else:
                print(f"golden-read: {label} failed — {row.get('message')}", file=sys.stderr)
        if report.get("status") == "ok":
            print("golden-read: all checks passed")
        else:
            print("golden-read: one or more dialogs failed", file=sys.stderr)
    return 0 if report.get("status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())