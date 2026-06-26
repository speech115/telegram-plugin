"""Shared MCP HTTP client helpers for fast CLI tools (tg, fast-read)."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

import httpx
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client


@dataclass(frozen=True)
class EndpointAttempt:
    endpoint: str
    env_file: str
    port: int


class McpCliError(RuntimeError):
    pass


TOOL_ERROR_PREFIXES = (
    "archive_route_blocked:",
    "confirmation_payload_mismatch:",
    "confirmation_rejected:",
    "expired_confirmation_token:",
    "human_approval_required:",
    "invalid_confirmation_token:",
    "invalid_context_mode:",
    "invalid_date_range:",
    "invalid_input:",
    "missing_confirmation_token:",
    "missing_send_target:",
    "permission_denied:",
    "rate_limited:",
    "telegram_tool_error:",
    "transport_unavailable:",
)


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
        raise McpCliError(f"TELEGRAM_MCP_ACCOUNT must be one of: {known}")

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
        lower = payload.strip().lower()
        return (
            "unknown tool" in lower
            or lower.startswith("error executing tool ")
            or "error executing tool " in lower
            or lower.startswith(TOOL_ERROR_PREFIXES)
        )
    if isinstance(payload, dict):
        message = payload.get("message") or payload.get("error")
        if message is not None and payload_is_tool_error(str(message)):
            return True
        code = payload.get("code") or payload.get("error_code")
        return code is not None and payload_is_tool_error(f"{code}:")
    return False


def result_is_tool_error(result, payload: object | None) -> bool:
    return bool(getattr(result, "isError", False)) or payload_is_tool_error(payload)


def tool_error_payload(result, payload: object | None) -> object | None:
    structured = getattr(result, "structuredContent", None)
    if structured is not None:
        return structured
    return payload


async def call_tool_once(
    *,
    attempt: EndpointAttempt,
    tool_name: str,
    arguments: dict[str, object],
    timeout: float,
) -> tuple[object | None, float, EndpointAttempt]:
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
                result = await session.call_tool(tool_name, arguments)

    payload = content_payload(result)
    if result_is_tool_error(result, payload):
        error_payload = tool_error_payload(result, payload)
        raise McpCliError(f"MCP tool error at {attempt.endpoint}: {error_payload!r}")

    elapsed_seconds = round(time.perf_counter() - started, 3)
    return payload, elapsed_seconds, attempt


async def list_tools_once(
    *,
    attempt: EndpointAttempt,
    timeout: float,
) -> tuple[list[str], float, EndpointAttempt]:
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
                result = await session.list_tools()

    names = [tool.name for tool in result.tools]
    elapsed_seconds = round(time.perf_counter() - started, 3)
    return names, elapsed_seconds, attempt


async def call_tool_with_failover(
    *,
    tool_name: str,
    arguments: dict[str, object],
    timeout: float,
    explicit_endpoint: str | None = None,
    env_file: str | Path | None = None,
    account: str | None = None,
) -> tuple[object | None, float, EndpointAttempt]:
    attempts = endpoint_attempts(
        explicit_endpoint=explicit_endpoint,
        primary_env_file=env_file,
        account=account,
    )
    errors: list[str] = []

    for attempt in attempts:
        try:
            return await call_tool_once(
                attempt=attempt,
                tool_name=tool_name,
                arguments=arguments,
                timeout=timeout,
            )
        except (
            httpx.TimeoutException,
            httpx.ConnectError,
            httpx.NetworkError,
            ConnectionError,
            OSError,
            McpCliError,
        ) as exc:
            errors.append(f"{attempt.endpoint}: {type(exc).__name__}: {exc}")

    raise McpCliError("; ".join(errors) or "no MCP endpoints configured")


async def list_tools_with_failover(
    *,
    timeout: float,
    explicit_endpoint: str | None = None,
    env_file: str | Path | None = None,
    account: str | None = None,
) -> tuple[list[str], float, EndpointAttempt]:
    attempts = endpoint_attempts(
        explicit_endpoint=explicit_endpoint,
        primary_env_file=env_file,
        account=account,
    )
    errors: list[str] = []

    for attempt in attempts:
        try:
            return await list_tools_once(attempt=attempt, timeout=timeout)
        except (
            httpx.TimeoutException,
            httpx.ConnectError,
            httpx.NetworkError,
            ConnectionError,
            OSError,
            McpCliError,
        ) as exc:
            errors.append(f"{attempt.endpoint}: {type(exc).__name__}: {exc}")

    raise McpCliError("; ".join(errors) or "no MCP endpoints configured")
