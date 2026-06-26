"""Fast read-only today dialog via local MCP HTTP with endpoint failover."""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import date
from pathlib import Path

import httpx

from .mcp_http_client import (
    ACCOUNT_ENDPOINTS,
    EndpointAttempt,
    McpToolError,
    call_tool_once,
    endpoint_attempts,
    payload_is_tool_error,
)


class FastReadError(RuntimeError):
    pass


def exception_is_tool_error(exc: Exception) -> bool:
    return isinstance(exc, McpToolError) or payload_is_tool_error(str(exc))


async def read_once(
    *,
    attempt: EndpointAttempt,
    chat: str,
    day: str,
    limit: int,
    voice: bool,
    sender_names: bool,
    timeout: float,
) -> dict[str, object]:
    mode = "full" if (voice or sender_names) else "fast"
    try:
        payload, elapsed_seconds, completed_attempt = await call_tool_once(
            attempt=attempt,
            tool_name="telegram_read",
            arguments={"chat": chat, "day": day, "limit": limit, "mode": mode},
            timeout=timeout,
        )
    except McpToolError as exc:
        raise FastReadError(str(exc)) from None

    from .agent_preflight import observe_fast_read
    from .telemetry import record_telemetry, telemetry_fields_from_result

    duration_ms = round(elapsed_seconds * 1000, 3)
    observe_fast_read(
        tool="fast_read",
        status="ok",
        source="fast_read_cli",
        duration_ms=duration_ms,
    )
    record_telemetry(
        "fast_read",
        status="ok",
        duration_ms=duration_ms,
        source="fast_read_cli",
        endpoint_port=completed_attempt.port or None,
        arg_chat=chat,
        arg_day=day,
        arg_limit=limit,
        **telemetry_fields_from_result(payload if isinstance(payload, dict) else None),
    )
    return {
        "ok": True,
        "mode": "telegram_fast_read_today",
        "endpoint": completed_attempt.endpoint,
        "endpoint_port": completed_attempt.port or None,
        "elapsed_seconds": elapsed_seconds,
        "payload": payload,
    }


async def read_with_failover(
    *,
    chat: str,
    day: str,
    limit: int,
    voice: bool,
    sender_names: bool,
    timeout: float,
    explicit_endpoint: str | None = None,
    env_file: str | Path | None = None,
    account: str | None = None,
) -> dict[str, object]:
    attempts = endpoint_attempts(
        explicit_endpoint=explicit_endpoint,
        primary_env_file=env_file,
        account=account,
    )
    errors: list[str] = []

    for attempt in attempts:
        try:
            return await read_once(
                attempt=attempt,
                chat=chat,
                day=day,
                limit=limit,
                voice=voice,
                sender_names=sender_names,
                timeout=timeout,
            )
        except (
            httpx.TimeoutException,
            httpx.ConnectError,
            httpx.NetworkError,
            ConnectionError,
            OSError,
        ) as exc:
            errors.append(f"{attempt.endpoint}: {type(exc).__name__}: {exc}")

    raise FastReadError("; ".join(errors) or "no MCP endpoints configured")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="telegram-fast-read-today",
        description="Fast read-only Telegram today dialog via the local MCP HTTP daemon.",
    )
    parser.add_argument("chat", help="@username, dialog ref, or peer id")
    parser.add_argument("--day", default=date.today().isoformat())
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--sender-names", action="store_true")
    parser.add_argument("--voice", action="store_true")
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument(
        "--account",
        choices=tuple(ACCOUNT_ENDPOINTS),
        default="main",
        help="Telegram account daemon to use.",
    )
    parser.add_argument(
        "--env-file",
        default="~/.telegram-mcp/launchd.env",
        help="Primary Telegram MCP env file; secrets are loaded but never printed.",
    )
    parser.add_argument("--endpoint", default=None, help="Explicit MCP HTTP endpoint URL.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        output = asyncio.run(
            read_with_failover(
                chat=args.chat,
                day=args.day,
                limit=args.limit,
                voice=args.voice,
                sender_names=args.sender_names,
                timeout=args.timeout,
                explicit_endpoint=args.endpoint,
                env_file=args.env_file,
                account=args.account,
            )
        )
    except Exception as exc:
        if exception_is_tool_error(exc):
            error = {
                "ok": False,
                "mode": "telegram_fast_read_today",
                "error_type": type(exc).__name__,
                "error": "telegram_tool_error",
                "message": "Live Telegram read failed inside the MCP tool.",
            }
        else:
            error = {
                "ok": False,
                "mode": "telegram_fast_read_today",
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
        print(
            json.dumps(
                error,
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1

    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
