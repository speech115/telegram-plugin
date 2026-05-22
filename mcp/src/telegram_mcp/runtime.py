"""FastMCP runtime and transport wiring."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from mcp.server.fastmcp import FastMCP

from .client import TelegramWrapper
from .config import get_settings

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
)

log = structlog.get_logger()
_shared_wrapper: TelegramWrapper | None = None
_shared_wrapper_lock = asyncio.Lock()


def shared_mode_enabled() -> bool:
    settings = get_settings()
    if settings.mcp_shared_client:
        return True
    return settings.mcp_transport.lower() in {"streamable-http", "sse"}


async def get_or_connect_shared_wrapper() -> TelegramWrapper:
    global _shared_wrapper

    async with _shared_wrapper_lock:
        if _shared_wrapper is None:
            settings = get_settings()
            wrapper = TelegramWrapper(settings)
            await wrapper.connect()
            _shared_wrapper = wrapper
            log.info("telegram_connected_shared")
        return _shared_wrapper


async def _disconnect_shared_wrapper() -> None:
    global _shared_wrapper

    async with _shared_wrapper_lock:
        if _shared_wrapper is not None:
            await _shared_wrapper.disconnect()
            _shared_wrapper = None
            log.info("telegram_disconnected_shared")


@asynccontextmanager
async def lifespan(server: FastMCP) -> AsyncIterator[dict]:
    """Connect Telegram client on startup, disconnect on shutdown."""
    if shared_mode_enabled():
        wrapper = await get_or_connect_shared_wrapper()
        # In stateless HTTP mode FastMCP creates a fresh server session for each
        # POST/GET request, so disconnecting here would tear down the global
        # shared Telegram client out from under concurrent requests.
        yield {"tg": wrapper}
        return

    settings = get_settings()
    wrapper = TelegramWrapper(settings)
    connected = False
    try:
        await wrapper.connect()
        connected = True
        log.info("telegram_connected")
        yield {"tg": wrapper}
    finally:
        if connected:
            await wrapper.disconnect()
            log.info("telegram_disconnected")


mcp = FastMCP(
    "telegram",
    instructions=(
        "Telegram MCP server — read chats, send messages, search, manage contacts and media. "
        "Chat identifiers accept: numeric ID, @username, phone number, 'me' (Saved Messages), or t.me link."
    ),
    lifespan=lifespan,
    warn_on_duplicate_tools=True,
    # Shell-oriented MCP clients like mcporter work more reliably when
    # streamable-http requests can complete with plain JSON instead of
    # falling back to 202 + SSE reconnection flow.
    json_response=True,
    stateless_http=True,
)


async def get_tg() -> TelegramWrapper:
    """Get TelegramWrapper from current request context, ensuring connection."""
    from mcp.server.fastmcp import Context

    ctx = mcp.get_context()
    tg = ctx.request_context.lifespan_context["tg"]
    await tg.ensure_connected()
    return tg


def read_transport() -> str:
    settings = get_settings()
    transport = settings.mcp_transport.strip().lower()
    if transport not in {"stdio", "sse", "streamable-http"}:
        raise ValueError(
            "Invalid TELEGRAM_MCP_TRANSPORT. "
            "Use one of: stdio, sse, streamable-http."
        )
    return transport


def read_port() -> int:
    settings = get_settings()
    port = settings.mcp_port
    if not (1 <= port <= 65535):
        raise ValueError("Invalid TELEGRAM_MCP_PORT. Must be in range 1..65535.")
    return port


def read_host() -> str:
    return get_settings().mcp_host


def read_http_path() -> str:
    return get_settings().mcp_http_path


def get_runtime_report() -> dict[str, object]:
    transport = read_transport()
    report: dict[str, object] = {
        "transport": transport,
        "shared_client": shared_mode_enabled(),
    }
    if transport == "stdio":
        report.update(
            {
                "host": None,
                "port": None,
                "http_path": None,
                "endpoint_url": None,
            }
        )
        return report

    host = read_host()
    port = read_port()
    http_path = read_http_path()
    report.update(
        {
            "host": host,
            "port": port,
            "http_path": http_path,
            "endpoint_url": f"http://{host}:{port}{http_path}",
        }
    )
    return report


def run_server() -> None:
    settings = get_settings()
    transport = read_transport()
    mcp.settings.json_response = settings.mcp_json_response

    if transport != "stdio":
        mcp.settings.host = settings.mcp_host
        mcp.settings.port = settings.mcp_port
        mcp.settings.streamable_http_path = settings.mcp_http_path
        mcp.settings.mount_path = settings.mcp_mount_path

    try:
        mcp.run(transport=transport)
    finally:
        if shared_mode_enabled():
            asyncio.run(_disconnect_shared_wrapper())
