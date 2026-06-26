"""Light MCP HTTP prewarm after daemon restart using the live read path."""

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from pathlib import Path

import httpx
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client

from .mcp_http_client import build_endpoint, endpoint_attempts, load_env_file


@dataclass(frozen=True)
class PrewarmAttemptResult:
    endpoint: str
    port: int
    status: str
    elapsed_seconds: float
    error: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class McpPrewarmResult:
    status: str
    attempts: list[PrewarmAttemptResult]

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "attempts": [item.to_dict() for item in self.attempts],
        }


async def _prewarm_endpoint(
    *,
    endpoint: str,
    env_file: str,
    port: int,
    timeout: float,
) -> PrewarmAttemptResult:
    started = time.perf_counter()
    if env_file:
        load_env_file(Path(env_file).expanduser())

    token = os.environ.get("TELEGRAM_MCP_AUTH_TOKEN", "").strip()
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    http_timeout = httpx.Timeout(
        timeout,
        connect=min(timeout, 3.0),
        read=timeout,
        write=timeout,
        pool=min(timeout, 3.0),
    )

    try:
        async with httpx.AsyncClient(headers=headers, timeout=http_timeout) as http_client:
            async with streamable_http_client(endpoint, http_client=http_client) as (
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
                    await session.call_tool(
                        "telegram_read",
                        {
                            "chat": "me",
                            "day": date.today().isoformat(),
                            "limit": 1,
                            "mode": "fast",
                        },
                    )
        return PrewarmAttemptResult(
            endpoint=endpoint,
            port=port,
            status="ok",
            elapsed_seconds=round(time.perf_counter() - started, 3),
        )
    except Exception as exc:  # noqa: BLE001 - aggregate per-endpoint failures
        return PrewarmAttemptResult(
            endpoint=endpoint,
            port=port,
            status="fail",
            elapsed_seconds=round(time.perf_counter() - started, 3),
            error=str(exc),
        )


async def prewarm_mcp_http_async(
    *,
    timeout: float = 8.0,
    ports: list[int] | None = None,
) -> McpPrewarmResult:
    host = os.environ.get("TELEGRAM_MCP_HOST", "127.0.0.1")
    path = os.environ.get("TELEGRAM_MCP_HTTP_PATH", "/mcp")
    if ports is None:
        attempts = endpoint_attempts()
    else:
        attempts = [
            endpoint_attempts(primary_port=port)[0]
            for port in ports
        ]

    results: list[PrewarmAttemptResult] = []
    for attempt in attempts:
        endpoint = attempt.endpoint or build_endpoint(host, attempt.port, path)
        results.append(
            await _prewarm_endpoint(
                endpoint=endpoint,
                env_file=attempt.env_file,
                port=attempt.port,
                timeout=timeout,
            )
        )

    ok_count = sum(1 for item in results if item.status == "ok")
    if ok_count == len(results) and results:
        status = "ok"
    elif ok_count:
        status = "partial"
    else:
        status = "fail"
    return McpPrewarmResult(status=status, attempts=results)


def prewarm_mcp_http(
    *,
    timeout: float = 8.0,
    ports: list[int] | None = None,
) -> McpPrewarmResult:
    return asyncio.run(prewarm_mcp_http_async(timeout=timeout, ports=ports))
