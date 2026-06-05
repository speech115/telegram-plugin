"""Small `tg` CLI for task-shaped local Telegram MCP reads."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from datetime import date, timedelta
from typing import Any

import httpx
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client


def endpoint_url() -> str:
    host = os.environ.get("TELEGRAM_MCP_HOST", "127.0.0.1")
    port = os.environ.get("TELEGRAM_MCP_PORT", "8799")
    path = os.environ.get("TELEGRAM_MCP_HTTP_PATH", "/mcp")
    if not path.startswith("/"):
        path = "/" + path
    return f"http://{host}:{port}{path}"


def content_payload(result: Any) -> object | None:
    if not result.content:
        return None
    text = getattr(result.content[0], "text", None)
    if text is None:
        return str(result.content[0])
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


async def call_tool(tool_name: str, arguments: dict[str, object], *, timeout: float) -> object | None:
    token = os.environ.get("TELEGRAM_MCP_AUTH_TOKEN", "").strip()
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    http_timeout = httpx.Timeout(timeout, connect=min(timeout, 3.0), read=timeout, write=timeout, pool=3.0)
    async with httpx.AsyncClient(headers=headers, timeout=http_timeout) as http_client:
        async with streamable_http_client(endpoint_url(), http_client=http_client) as (read_stream, write_stream, _):
            async with ClientSession(
                read_stream,
                write_stream,
                read_timeout_seconds=timedelta(seconds=timeout),
            ) as session:
                await session.initialize()
                result = await session.call_tool(tool_name, arguments)
    return content_payload(result)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tg",
        description="Fast live Telegram reads and search via local MCP.",
    )
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--timeout", type=float, default=20.0)

    sub = parser.add_subparsers(dest="command", required=True)
    read = sub.add_parser("read", help="Read live Telegram messages")
    read_sub = read.add_subparsers(dest="read_mode", required=True)

    today = read_sub.add_parser("today", help="Read messages for one calendar day")
    today.add_argument("chat")
    today.add_argument("--day", default=date.today().isoformat())
    today.add_argument("--limit", type=int, default=30)

    recent = read_sub.add_parser("recent", help="Read recent messages")
    recent.add_argument("chat")
    recent.add_argument("--limit", type=int, default=30)

    search = sub.add_parser("search", help="Search one dialog")
    search.add_argument("chat")
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=20)

    doctor = sub.add_parser("doctor", help="Run doctor_check")
    doctor.set_defaults(read_mode=None)
    return parser


async def run(args: argparse.Namespace) -> dict[str, object]:
    if args.command == "doctor":
        payload = await call_tool("doctor_check", {}, timeout=args.timeout)
        return {"ok": True, "command": "doctor", "payload": payload}
    if args.command == "search":
        payload = await call_tool(
            "telegram_search",
            {"chat": args.chat, "query": args.query, "limit": args.limit},
            timeout=args.timeout,
        )
        return {"ok": True, "command": "search", "payload": payload}
    if args.read_mode == "today":
        payload = await call_tool(
            "telegram_read",
            {"chat": args.chat, "day": args.day, "limit": args.limit, "mode": "fast"},
            timeout=args.timeout,
        )
        return {"ok": True, "command": "read today", "payload": payload}
    payload = await call_tool(
        "telegram_read",
        {"chat": args.chat, "limit": args.limit, "mode": "fast"},
        timeout=args.timeout,
    )
    return {"ok": True, "command": "read recent", "payload": payload}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = asyncio.run(run(args))
    print(json.dumps(result if args.json else result["payload"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
