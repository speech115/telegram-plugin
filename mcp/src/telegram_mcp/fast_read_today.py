"""Fast read-only today dialog via local MCP HTTP with endpoint failover."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from pathlib import Path

import httpx
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client


@dataclass(frozen=True)
class EndpointAttempt:
    endpoint: str
    env_file: str
    port: int


class FastReadError(RuntimeError):
    pass


ACCOUNT_ENDPOINTS = {
    "main": (8799, "~/.telegram-mcp/launchd.env"),
    "crwddy": (8799, "~/.telegram-mcp/launchd.env"),
    "pl": (8800, "~/.telegram-mcp-pl/launchd.env"),
    "recklessou": (8801, "~/.telegram-mcp-recklessou/launchd.env"),
    "teamsyncsage": (8802, "~/.telegram-mcp-teamsyncsage/launchd.env"),
    "vermassov": (8803, "~/.telegram-mcp-vermassov/launchd.env"),
}


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :]
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'\"")
        if key.startswith("TELEGRAM_") and key not in os.environ:
            os.environ[key] = value


def build_endpoint(host: str, port: int, path: str) -> str:
    if not path.startswith("/"):
        path = "/" + path
    return f"http://{host}:{port}{path}"


def endpoint_attempts(
    *,
    explicit_endpoint: str | None = None,
    host: str | None = None,
    account: str | None = None,
    primary_port: int | None = None,
    failover_ports: list[int] | None = None,
    primary_env_file: str | Path | None = None,
    pl_env_file: str | Path | None = None,
) -> list[EndpointAttempt]:
    if explicit_endpoint:
        return [EndpointAttempt(endpoint=explicit_endpoint, env_file=str(primary_env_file or ""), port=0)]

    host_name = host or os.environ.get("TELEGRAM_MCP_HOST", "127.0.0.1")
    path = os.environ.get("TELEGRAM_MCP_HTTP_PATH", "/mcp")
    selected_account = (account or os.environ.get("TELEGRAM_MCP_ACCOUNT", "main")).strip().lower()
    account_config = ACCOUNT_ENDPOINTS.get(selected_account)
    if account_config is None:
        known = ", ".join(sorted(ACCOUNT_ENDPOINTS))
        raise FastReadError(f"TELEGRAM_MCP_ACCOUNT must be one of: {known}")

    account_port, account_env_file = account_config
    primary = primary_port or account_port
    extra = failover_ports
    if extra is None:
        raw = os.environ.get("TELEGRAM_MCP_FAILOVER_PORTS", "")
        extra = [int(item.strip()) for item in raw.split(",") if item.strip()]

    ports: list[int] = []
    for candidate in [primary, *extra]:
        if candidate not in ports:
            ports.append(candidate)

    selected_env = Path(primary_env_file or account_env_file).expanduser()

    attempts: list[EndpointAttempt] = []
    for port in ports:
        attempts.append(
            EndpointAttempt(
                endpoint=build_endpoint(host_name, port, path),
                env_file=str(selected_env),
                port=port,
            )
        )
    return attempts


def content_payload(result) -> object | None:
    if not result.content:
        return None
    first = result.content[0]
    text = getattr(first, "text", None)
    if text is None:
        return str(first)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def payload_is_tool_error(payload: object | None) -> bool:
    if isinstance(payload, str):
        lower = payload.lower()
        return (
            "unknown tool" in lower
            or lower.startswith("error executing tool ")
            or "error executing tool " in lower
        )
    if isinstance(payload, dict):
        message = str(payload.get("message") or payload.get("error") or "")
        return payload_is_tool_error(message)
    return False


def exception_is_tool_error(exc: Exception) -> bool:
    return payload_is_tool_error(str(exc))


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
    if attempt.env_file:
        load_env_file(Path(attempt.env_file).expanduser())

    token = os.environ.get("TELEGRAM_MCP_AUTH_TOKEN", "").strip()
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    http_timeout = httpx.Timeout(
        timeout,
        connect=min(timeout, 3.0),
        read=timeout,
        write=timeout,
        pool=min(timeout, 3.0),
    )

    started = time.perf_counter()
    async with httpx.AsyncClient(headers=headers, timeout=http_timeout) as http_client:
        async with streamable_http_client(attempt.endpoint, http_client=http_client) as (
            read_stream,
            write_stream,
            _,
        ):
            async with ClientSession(
                read_stream,
                write_stream,
                read_timeout_seconds=timedelta(seconds=timeout),
            ) as session:
                await session.initialize()
                mode = "full" if (voice or sender_names) else "fast"
                result = await session.call_tool(
                    "telegram_read",
                    {
                        "chat": chat,
                        "day": day,
                        "limit": limit,
                        "mode": mode,
                    },
                )

    payload = content_payload(result)
    if payload_is_tool_error(payload):
        raise FastReadError(f"MCP tool error at {attempt.endpoint}: {payload!r}")

    elapsed_seconds = round(time.perf_counter() - started, 3)
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
        endpoint_port=attempt.port or None,
        arg_chat=chat,
        arg_day=day,
        arg_limit=limit,
        **telemetry_fields_from_result(payload if isinstance(payload, dict) else None),
    )
    return {
        "ok": True,
        "mode": "telegram_fast_read_today",
        "endpoint": attempt.endpoint,
        "endpoint_port": attempt.port or None,
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
            FastReadError,
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
