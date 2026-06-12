from __future__ import annotations

import argparse
import json
import sys
from collections import deque
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml

from .paths import MIRROR_RUNTIME_ROOT

EXPORT_ROOT = MIRROR_RUNTIME_ROOT / "runtime/ingest/telegram/exports"
CONFIG_ROOT = MIRROR_RUNTIME_ROOT / "config"
LEDGER_ROOT = MIRROR_RUNTIME_ROOT / "data/telegram_sync"


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value.strip())


def _row_date(row: dict[str, Any]) -> date | None:
    raw = str(row.get("date") or row.get("timestamp") or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(raw[:10])
        except ValueError:
            return None


def _row_text(row: dict[str, Any]) -> str:
    text = str(row.get("text_markdown") or row.get("text_raw") or row.get("message") or "").strip()
    if text:
        return text
    media_type = str(row.get("media_type") or "").strip()
    return f"[media:{media_type}]" if media_type else "[empty]"


def _message_payload(row: dict[str, Any], *, source: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": int(row.get("id") or row.get("message_id") or 0),
        "date": row.get("date") or row.get("timestamp"),
        "text": _row_text(row),
        "media_type": row.get("media_type"),
        "views": row.get("views"),
        "forwards": row.get("forwards"),
        "source": source,
    }


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def _config_rows(config_root: Path = CONFIG_ROOT) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not config_root.exists():
        return rows
    for path in sorted(config_root.glob("telegram_channels*.yaml")):
        try:
            payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError):
            continue
        for row in payload.get("channels", []):
            if not isinstance(row, dict):
                continue
            item = dict(row)
            item["_config_path"] = str(path)
            rows.append(item)
    return rows


def _norm(value: Any) -> str:
    return str(value or "").strip().lower().lstrip("@")


def _matches(row: dict[str, Any], query: str) -> bool:
    needle = _norm(query)
    if not needle:
        return False
    fields = (
        row.get("name"),
        row.get("username"),
        row.get("channel_id"),
        row.get("author_id"),
        row.get("speaker_name"),
        row.get("mirror_scope"),
        row.get("export_folder"),
    )
    return any(needle in _norm(value) for value in fields)


def _source_for(row: dict[str, Any], messages_path: Path) -> dict[str, Any]:
    return {
        "channel_id": row.get("channel_id"),
        "name": row.get("name"),
        "username": row.get("username"),
        "mirror_scope": row.get("mirror_scope"),
        "export_folder": row.get("export_folder"),
        "messages_path": str(messages_path),
    }


def _messages_path(row: dict[str, Any], export_root: Path = EXPORT_ROOT) -> Path:
    return export_root / str(row.get("export_folder") or "").strip() / "messages_raw.jsonl"


def build_status(*, export_root: Path = EXPORT_ROOT, ledger_root: Path = LEDGER_ROOT) -> dict[str, Any]:
    exports = sorted(export_root.glob("**/messages_raw.jsonl")) if export_root.exists() else []
    ledgers = sorted(ledger_root.glob("*.json")) if ledger_root.exists() else []
    return {
        "status": "ok" if MIRROR_RUNTIME_ROOT.exists() else "warn",
        "mode": "read_only_fast_mirror",
        "runtime_root": str(MIRROR_RUNTIME_ROOT),
        "runtime_root_exists": MIRROR_RUNTIME_ROOT.exists(),
        "export_root": str(export_root),
        "export_root_exists": export_root.exists(),
        "export_count": len(exports),
        "ledger_root": str(ledger_root),
        "ledger_count": len(ledgers),
        "config_channel_count": len(_config_rows()),
        "commands": {
            "read": "telegram-mirror-fast read <channel> --limit 30 --json",
            "search": "telegram-mirror-fast search <text> --limit 30 --json",
        },
    }


def read_messages(
    *,
    query: str,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 30,
    config_root: Path = CONFIG_ROOT,
    export_root: Path = EXPORT_ROOT,
) -> dict[str, Any]:
    matches = [row for row in _config_rows(config_root) if _matches(row, query)]
    if not matches:
        return {"status": "warn", "error": "mirror_target_not_found", "query": query, "messages": [], "message_count": 0}

    start = _parse_date(date_from)
    end = _parse_date(date_to)
    if start and end and start > end:
        raise ValueError("--date-from must be before or equal to --date-to")

    messages: deque[dict[str, Any]] = deque(maxlen=max(limit, 0) or None)
    missing_exports: list[dict[str, Any]] = []
    for row in matches:
        path = _messages_path(row, export_root)
        source = _source_for(row, path)
        if not path.exists():
            missing_exports.append(source)
            continue
        for raw in _load_jsonl(path):
            msg_date = _row_date(raw)
            if start and (msg_date is None or msg_date < start):
                continue
            if end and (msg_date is None or msg_date > end):
                continue
            messages.append(_message_payload(raw, source=source))

    result = list(messages)
    result.sort(key=lambda row: (str(row.get("date") or ""), int(row.get("id") or 0)))
    return {
        "status": "ok" if result else "warn",
        "query": query,
        "range": {"date_from": date_from, "date_to": date_to},
        "matched_targets": len(matches),
        "missing_exports": missing_exports,
        "message_count": len(result),
        "messages": result,
    }


def search_messages(
    *,
    text: str,
    target: str | None = None,
    limit: int = 30,
    config_root: Path = CONFIG_ROOT,
    export_root: Path = EXPORT_ROOT,
) -> dict[str, Any]:
    needle = text.casefold()
    rows = _config_rows(config_root)
    if target:
        rows = [row for row in rows if _matches(row, target)]
    hits: list[dict[str, Any]] = []
    for row in rows:
        path = _messages_path(row, export_root)
        if not path.exists():
            continue
        source = _source_for(row, path)
        for raw in _load_jsonl(path):
            body = _row_text(raw)
            if needle in body.casefold():
                hits.append(_message_payload(raw, source=source))

    hits.sort(key=lambda row: (str(row.get("date") or ""), int(row.get("id") or 0)), reverse=True)
    return {
        "status": "ok" if hits else "warn",
        "query": text,
        "target": target,
        "message_count": min(len(hits), max(limit, 0)),
        "total_hits": len(hits),
        "messages": hits[: max(limit, 0)],
    }


def _render_text(payload: dict[str, Any]) -> str:
    lines = [f"status: {payload.get('status')}"]
    if payload.get("mode"):
        lines.append(f"mode: {payload['mode']}")
    for key in ("export_count", "ledger_count", "message_count", "total_hits"):
        if key in payload:
            lines.append(f"{key}: {payload[key]}")
    for msg in payload.get("messages", [])[:10]:
        source = msg.get("source") if isinstance(msg.get("source"), dict) else {}
        lines.append(f"- {msg.get('date')} {source.get('name')}: {msg.get('text')}")
    if payload.get("error"):
        lines.append(f"error: {payload['error']}")
    return "\n".join(lines)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fast read-only Telegram mirror commands")
    subparsers = parser.add_subparsers(dest="command", required=True)

    status = subparsers.add_parser("status", help="Show fast mirror file status")
    status.add_argument("--json", action="store_true")

    read = subparsers.add_parser("read", help="Read messages from one mirrored channel/chat")
    read.add_argument("query")
    read.add_argument("--date-from")
    read.add_argument("--date-to")
    read.add_argument("--limit", type=int, default=30)
    read.add_argument("--json", action="store_true")

    search = subparsers.add_parser("search", help="Search mirrored channel/chat exports")
    search.add_argument("text")
    search.add_argument("--target", help="Optional channel/chat filter")
    search.add_argument("--limit", type=int, default=30)
    search.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if args.command == "status":
        payload = build_status()
    elif args.command == "read":
        payload = read_messages(query=args.query, date_from=args.date_from, date_to=args.date_to, limit=args.limit)
    else:
        payload = search_messages(text=args.text, target=args.target, limit=args.limit)

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(_render_text(payload))
    return 1 if payload.get("status") == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
