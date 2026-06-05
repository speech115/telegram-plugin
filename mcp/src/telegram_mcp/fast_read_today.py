"""Fast read-only CLI wrapper for today's dialog messages."""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import date

from .tg_cli import call_tool


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="telegram-fast-read-today",
        description="Read one live Telegram dialog for a calendar day via telegram_read.",
    )
    parser.add_argument("chat")
    parser.add_argument("--day", default=date.today().isoformat())
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--timeout", type=float, default=20.0)
    return parser


async def run(args: argparse.Namespace) -> dict[str, object]:
    payload = await call_tool(
        "telegram_read",
        {
            "chat": args.chat,
            "day": args.day,
            "limit": args.limit,
            "mode": "fast",
        },
        timeout=args.timeout,
    )
    return {"ok": True, "command": "read today", "payload": payload}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = asyncio.run(run(args))
    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(json.dumps(result["payload"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
