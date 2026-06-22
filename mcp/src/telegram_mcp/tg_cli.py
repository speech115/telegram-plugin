"""Unified `tg` CLI: fast live reads and search via local MCP HTTP (no plugin bootstrap)."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import date

from .mcp_http_client import ACCOUNT_ENDPOINTS, McpCliError, call_tool_with_failover
from .telemetry import record_telemetry, telemetry_fields_from_result


def _payload_is_tool_error(payload: object | None) -> bool:
    if isinstance(payload, str):
        lower = payload.lower()
        return "unknown tool" in lower or "error executing tool " in lower
    if isinstance(payload, dict):
        return _payload_is_tool_error(payload.get("error") or payload.get("message"))
    return False


def _wrap_ok(
    *,
    command: str,
    endpoint: str,
    endpoint_port: int | None,
    elapsed_seconds: float,
    payload: object | None,
    intent: str,
) -> dict[str, object]:
    data_source = None
    if isinstance(payload, dict):
        data_source = payload.get("data_source")
    if _payload_is_tool_error(payload):
        wrapped = {
            "ok": False,
            "command": command,
            "intent": intent,
            "data_source": data_source or "live_telegram",
            "endpoint": endpoint,
            "endpoint_port": endpoint_port,
            "elapsed_seconds": elapsed_seconds,
            "error": "telegram_tool_error",
            "message": "Live Telegram tool returned an error payload.",
        }
        if isinstance(payload, dict):
            wrapped["tool_error_payload"] = payload
        elif isinstance(payload, str):
            wrapped["tool_error_payload"] = payload[:2000]
        return wrapped
    return {
        "ok": True,
        "command": command,
        "intent": intent,
        "data_source": data_source or "live_telegram",
        "endpoint": endpoint,
        "endpoint_port": endpoint_port,
        "elapsed_seconds": elapsed_seconds,
        "payload": payload,
    }


def _wrap_err(*, command: str, exc: Exception) -> dict[str, object]:
    return {
        "ok": False,
        "command": command,
        "error_type": type(exc).__name__,
        "error": str(exc),
    }


async def cmd_doctor(*, timeout: float, endpoint: str | None, env_file: str | None, account: str) -> dict[str, object]:
    payload, elapsed, attempt = await call_tool_with_failover(
        tool_name="doctor_check",
        arguments={},
        timeout=timeout,
        explicit_endpoint=endpoint,
        env_file=env_file,
        account=account,
    )
    return _wrap_ok(
        command="doctor",
        endpoint=attempt.endpoint,
        endpoint_port=attempt.port or None,
        elapsed_seconds=elapsed,
        payload=payload,
        intent="health",
    )


async def cmd_read_today(
    *,
    chat: str,
    day: str,
    limit: int,
    timeout: float,
    endpoint: str | None,
    env_file: str | None,
    account: str,
) -> dict[str, object]:
    payload, elapsed, attempt = await call_tool_with_failover(
        tool_name="telegram_read",
        arguments={"chat": chat, "day": day, "limit": limit, "mode": "fast"},
        timeout=timeout,
        explicit_endpoint=endpoint,
        env_file=env_file,
        account=account,
    )
    duration_ms = round(elapsed * 1000, 3)
    from .agent_preflight import observe_fast_read

    observe_fast_read(tool="tg_read_today", status="ok", source="tg_cli", duration_ms=duration_ms)
    record_telemetry(
        "tg_read_today",
        status="ok",
        duration_ms=duration_ms,
        source="tg_cli",
        endpoint_port=attempt.port or None,
        arg_chat=chat,
        arg_day=day,
        arg_limit=limit,
        **telemetry_fields_from_result(payload if isinstance(payload, dict) else None),
    )
    return _wrap_ok(
        command="read today",
        endpoint=attempt.endpoint,
        endpoint_port=attempt.port or None,
        elapsed_seconds=elapsed,
        payload=payload,
        intent="live_today",
    )


async def cmd_read_recent(
    *,
    chat: str,
    limit: int,
    timeout: float,
    endpoint: str | None,
    env_file: str | None,
    account: str,
) -> dict[str, object]:
    payload, elapsed, attempt = await call_tool_with_failover(
        tool_name="telegram_read",
        arguments={"chat": chat, "limit": limit, "mode": "fast"},
        timeout=timeout,
        explicit_endpoint=endpoint,
        env_file=env_file,
        account=account,
    )
    record_telemetry(
        "tg_read_recent",
        status="ok",
        duration_ms=round(elapsed * 1000, 3),
        source="tg_cli",
        endpoint_port=attempt.port or None,
        arg_chat=chat,
        arg_limit=limit,
        **telemetry_fields_from_result(payload if isinstance(payload, dict) else None),
    )
    return _wrap_ok(
        command="read recent",
        endpoint=attempt.endpoint,
        endpoint_port=attempt.port or None,
        elapsed_seconds=elapsed,
        payload=payload,
        intent="live_recent",
    )


async def cmd_search(
    *,
    chat: str,
    query: str,
    limit: int,
    timeout: float,
    endpoint: str | None,
    env_file: str | None,
    account: str,
) -> dict[str, object]:
    payload, elapsed, attempt = await call_tool_with_failover(
        tool_name="telegram_search",
        arguments={"chat": chat, "query": query, "limit": limit},
        timeout=timeout,
        explicit_endpoint=endpoint,
        env_file=env_file,
        account=account,
    )
    record_telemetry(
        "tg_search",
        status="ok",
        duration_ms=round(elapsed * 1000, 3),
        source="tg_cli",
        endpoint_port=attempt.port or None,
        arg_chat=chat,
        **telemetry_fields_from_result(payload if isinstance(payload, dict) else None),
    )
    return _wrap_ok(
        command="search",
        endpoint=attempt.endpoint,
        endpoint_port=attempt.port or None,
        elapsed_seconds=elapsed,
        payload=payload,
        intent="live_search",
    )


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", help="Emit JSON envelope.")
    common.add_argument("--timeout", type=float, default=20.0)
    common.add_argument("--env-file", default="~/.telegram-mcp/launchd.env")
    common.add_argument("--endpoint", default=None)
    common.add_argument("--account", choices=tuple(ACCOUNT_ENDPOINTS), default="main")

    parser = argparse.ArgumentParser(
        prog="tg",
        description="Fast live Telegram reads via local MCP (skill-first, no @telegram).",
    )
    parser.add_argument("--json", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--timeout", type=float, default=20.0, help=argparse.SUPPRESS)
    parser.add_argument("--env-file", default="~/.telegram-mcp/launchd.env", help=argparse.SUPPRESS)
    parser.add_argument("--endpoint", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--account", choices=tuple(ACCOUNT_ENDPOINTS), default="main", help=argparse.SUPPRESS)

    sub = parser.add_subparsers(dest="command", required=True)

    doctor = sub.add_parser("doctor", parents=[common], help="Light MCP health via doctor_check")
    doctor.set_defaults(handler="doctor")

    read = sub.add_parser("read", parents=[common], help="Live read (today or recent)")
    read_sub = read.add_subparsers(dest="read_mode", required=True)

    today = read_sub.add_parser("today", parents=[common], help="Messages for one calendar day (live only)")
    today.add_argument("chat")
    today.add_argument("--day", default=date.today().isoformat())
    today.add_argument("--limit", type=int, default=30)
    today.set_defaults(handler="read_today")

    recent = read_sub.add_parser("recent", parents=[common], help="Recent live messages (not archive)")
    recent.add_argument("chat")
    recent.add_argument("--limit", type=int, default=30)
    recent.set_defaults(handler="read_recent")

    search = sub.add_parser("search", parents=[common], help="Search within one live dialog")
    search.add_argument("chat")
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=20)
    search.set_defaults(handler="search")

    return parser


async def run_command(args: argparse.Namespace) -> dict[str, object]:
    env_file = args.env_file
    endpoint = args.endpoint
    timeout = args.timeout
    account = args.account

    if args.handler == "doctor":
        return await cmd_doctor(timeout=timeout, endpoint=endpoint, env_file=env_file, account=account)
    if args.handler == "read_today":
        return await cmd_read_today(
            chat=args.chat,
            day=args.day,
            limit=args.limit,
            timeout=timeout,
            endpoint=endpoint,
            env_file=env_file,
            account=account,
        )
    if args.handler == "read_recent":
        return await cmd_read_recent(
            chat=args.chat,
            limit=args.limit,
            timeout=timeout,
            endpoint=endpoint,
            env_file=env_file,
            account=account,
        )
    if args.handler == "search":
        return await cmd_search(
            chat=args.chat,
            query=args.query,
            limit=args.limit,
            timeout=timeout,
            endpoint=endpoint,
            env_file=env_file,
            account=account,
        )
    raise McpCliError(f"unknown handler: {args.handler}")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        output = asyncio.run(run_command(args))
    except Exception as exc:
        output = _wrap_err(command=getattr(args, "handler", "unknown"), exc=exc)

    if args.json or not sys.stdout.isatty():
        print(json.dumps(output, ensure_ascii=False, indent=2))
    elif output.get("ok"):
        print(f"ok: {output.get('command')} in {output.get('elapsed_seconds')}s")
        payload = output.get("payload")
        if isinstance(payload, dict) and "messages" in payload:
            print(f"messages: {len(payload.get('messages') or [])}")
    else:
        print(f"error: {output.get('error')}", file=sys.stderr)

    return 0 if output.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
