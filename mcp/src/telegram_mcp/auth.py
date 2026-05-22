"""Interactive Telegram login."""

import asyncio
import json
import sys
from datetime import timedelta
from pathlib import Path

import httpx
from telethon import TelegramClient

from .client import TelegramWrapper
from .config import get_settings
from .download_cleanup import estimate_download_cleanup
from .locking import FileSessionLock
from .runtime import get_runtime_report


async def interactive_login() -> None:
    settings = get_settings()
    settings.ensure_dirs()
    session_lock = None

    if settings.uses_file_session:
        print(f"Session will be saved to: {settings.session_path}")
        session_lock = FileSessionLock(settings.session_dir / "session.lock")
        session_lock.acquire()
    else:
        print("Using TELEGRAM_SESSION_STRING from environment.")

    client = TelegramClient(
        settings.build_session(),
        settings.api_id,
        settings.api_hash,
    )
    started = False

    try:
        await client.start()
        started = True

        me = await client.get_me()
        name = me.first_name or ""
        if me.last_name:
            name += f" {me.last_name}"
        print(f"Logged in as: {name} (@{me.username or 'N/A'})")
        print("Session saved. You can now run the MCP server.")
    finally:
        try:
            if started:
                await client.disconnect()
        finally:
            if session_lock is not None:
                session_lock.release()


async def get_health_report() -> dict[str, object]:
    settings = get_settings()
    runtime_report = get_runtime_report()

    if runtime_report["transport"] != "stdio":
        try:
            await _probe_http_runtime(
                str(runtime_report["endpoint_url"]),
                transport=str(runtime_report["transport"]),
                timeout_seconds=float(getattr(settings, "mcp_probe_timeout_seconds", 15.0)),
            )
            return {
                "connected": True,
                "authorized": True,
                "session_backend": settings.session_backend,
                "entity_cache_size": 0,
                "download_dir": str(settings.download_dir),
                "session_path": (
                    str(settings.session_path)
                    if settings.uses_file_session
                    else None
                ),
                **runtime_report,
            }
        except Exception as exc:
            return {
                "connected": False,
                "authorized": False,
                "session_backend": settings.session_backend,
                "entity_cache_size": 0,
                "download_dir": str(settings.download_dir),
                "session_path": (
                    str(settings.session_path)
                    if settings.uses_file_session
                    else None
                ),
                **runtime_report,
                "error": f"{type(exc).__name__}: {exc}",
            }

    wrapper = TelegramWrapper(settings)
    connected = False

    try:
        await wrapper.connect()
        connected = True
        return {
            **(await wrapper.health_check()).model_dump(mode="json"),
            **runtime_report,
        }
    except Exception as exc:
        return {
            "connected": False,
            "authorized": False,
            "session_backend": settings.session_backend,
            "entity_cache_size": 0,
            "download_dir": str(settings.download_dir),
            "session_path": (
                str(settings.session_path)
                if settings.uses_file_session
                else None
            ),
            **runtime_report,
            "error": f"{type(exc).__name__}: {exc}",
        }
    finally:
        if connected:
            await wrapper.disconnect()


async def get_doctor_report() -> dict[str, object]:
    settings = get_settings()
    runtime_report = get_runtime_report()

    if runtime_report["transport"] != "stdio":
        checks: dict[str, str] = {
            "transport": str(runtime_report["transport"]),
        }
        warnings: list[str] = []
        download_cleanup: dict[str, object] | None = None
        scheduler = _scheduler_config_snapshot(settings)
        runtime_stats: dict[str, object] | None = None
        checks["scheduler"] = "configured"

        try:
            settings.ensure_dirs()
            checks["download_dir"] = "ok"
            cleanup = estimate_download_cleanup(
                Path(settings.download_dir),
                getattr(settings, "download_retention_days", 0),
            )
            download_cleanup = cleanup.to_dict()
            checks["download_cleanup"] = "enabled" if cleanup.enabled else "disabled"
        except Exception as exc:
            checks["download_dir"] = "error"
            warnings.append(f"download_dir: {type(exc).__name__}: {exc}")

        if settings.uses_file_session:
            checks["session_backend"] = "sqlite"
            checks["session_dir"] = (
                "ok" if settings.session_dir.exists() else "missing"
            )
            checks["session_lock"] = "daemon-managed"
        else:
            checks["session_backend"] = "string"
            checks["session_dir"] = "disabled"
            checks["session_lock"] = "disabled"

        try:
            daemon_doctor = await _probe_http_runtime(
                str(runtime_report["endpoint_url"]),
                transport=str(runtime_report["transport"]),
                timeout_seconds=float(getattr(settings, "mcp_probe_timeout_seconds", 15.0)),
                include_doctor=True,
            )
            checks["listener"] = "ok"
            checks["initialize"] = "ok"
            checks["tool_call"] = "ok"
            checks["connection"] = "connected"
            if daemon_doctor is not None:
                scheduler = daemon_doctor.get("scheduler", scheduler)
                maybe_runtime_stats = daemon_doctor.get("runtime_stats")
                if isinstance(maybe_runtime_stats, dict):
                    runtime_stats = maybe_runtime_stats
                checks["scheduler"] = "live"
            status = "ok"
        except Exception as exc:
            checks["listener"] = "error"
            checks["initialize"] = "error"
            checks["tool_call"] = "error"
            checks["connection"] = "error"
            warnings.append(f"daemon_probe: {type(exc).__name__}: {exc}")
            status = "warn"

        if any(value in {"error", "missing"} for value in checks.values()):
            status = "warn"

        return {
            "status": status,
            "transport": str(runtime_report["transport"]),
            "session_backend": settings.session_backend,
            "checks": checks,
            "warnings": warnings,
            "download_cleanup": download_cleanup,
            "scheduler": scheduler,
            "runtime_stats": runtime_stats,
            **runtime_report,
        }

    wrapper = TelegramWrapper(settings)
    connected = False

    doctor = await wrapper.doctor_check()
    checks = dict(doctor.checks)
    warnings = list(doctor.warnings)
    status = doctor.status

    try:
        await wrapper.connect()
        connected = True
        checks["connect"] = "ok"
        checks["authorized"] = "ok"
    except Exception as exc:
        checks["connect"] = "error"
        warnings.append(f"connect: {type(exc).__name__}: {exc}")
        status = "warn"
    finally:
        if connected:
            await wrapper.disconnect()

    doctor = doctor.model_copy(
        update={
            "status": status,
            "checks": checks,
            "warnings": warnings,
        }
    )
    return {
        **doctor.model_dump(mode="json"),
        **runtime_report,
    }


def _scheduler_config_snapshot(settings) -> dict[str, dict[str, object]]:
    return {
        "read": {
            "limit": max(1, int(getattr(settings, "scheduler_read_concurrency", 4))),
            "timeout_seconds": float(getattr(settings, "tool_read_timeout_seconds", 30.0)),
        },
        "write": {
            "limit": max(1, int(getattr(settings, "scheduler_write_concurrency", 1))),
            "timeout_seconds": float(getattr(settings, "tool_write_timeout_seconds", 30.0)),
        },
        "media": {
            "limit": max(1, int(getattr(settings, "scheduler_media_concurrency", 2))),
            "timeout_seconds": float(getattr(settings, "tool_media_timeout_seconds", 120.0)),
        },
        "transcribe": {
            "limit": max(1, int(getattr(settings, "scheduler_transcribe_concurrency", 1))),
            "timeout_seconds": float(getattr(settings, "tool_transcribe_timeout_seconds", 45.0)),
        },
        "enrich": {
            "limit": max(1, int(getattr(settings, "scheduler_enrich_concurrency", 4))),
            "timeout_seconds": float(getattr(settings, "tool_enrich_timeout_seconds", 15.0)),
        },
        "circuit_breaker": {
            "enabled": bool(getattr(settings, "circuit_breaker_enabled", True)),
            "failure_threshold": max(
                1,
                int(getattr(settings, "circuit_breaker_failure_threshold", 3)),
            ),
            "recovery_seconds": float(
                getattr(settings, "circuit_breaker_recovery_seconds", 30.0)
            ),
        },
    }


async def _probe_http_runtime(
    endpoint_url: str,
    *,
    transport: str = "streamable-http",
    timeout_seconds: float = 15.0,
    include_doctor: bool = False,
) -> dict[str, object] | None:
    from mcp.client.session import ClientSession

    read_timeout = timedelta(seconds=timeout_seconds)
    settings = get_settings()
    auth_token = (getattr(settings, "mcp_auth_token", None) or "").strip()
    headers = {"Authorization": f"Bearer {auth_token}"} if auth_token else None

    if transport == "sse":
        from mcp.client.sse import sse_client

        async with sse_client(endpoint_url, headers=headers) as (read_stream, write_stream):
            async with ClientSession(
                read_stream,
                write_stream,
                read_timeout_seconds=read_timeout,
            ) as session:
                return await _probe_mcp_session(
                    session,
                    read_timeout=read_timeout,
                    include_doctor=include_doctor,
                )

    if transport != "streamable-http":
        raise ValueError(f"Unsupported daemon probe transport: {transport}")

    from mcp.client.streamable_http import streamable_http_client

    http_client = httpx.AsyncClient(headers=headers or {})
    async with http_client:
        streamable_client = streamable_http_client(endpoint_url, http_client=http_client)
        async with streamable_client as (
            read_stream,
            write_stream,
            _,
        ):
            async with ClientSession(
                read_stream,
                write_stream,
                read_timeout_seconds=read_timeout,
            ) as session:
                return await _probe_mcp_session(
                    session,
                    read_timeout=read_timeout,
                    include_doctor=include_doctor,
                )


async def _probe_mcp_session(
    session,
    *,
    read_timeout: timedelta,
    include_doctor: bool,
) -> dict[str, object] | None:
    await session.initialize()
    result = await session.call_tool(
        "get_me",
        read_timeout_seconds=read_timeout,
    )
    if result.isError:
        raise RuntimeError("daemon get_me probe returned isError=true")
    if not include_doctor:
        return None

    list_tools = getattr(session, "list_tools", None)
    if list_tools is not None:
        tools_result = await list_tools()
        tools = getattr(tools_result, "tools", [])
        if not any(getattr(tool, "name", None) == "doctor_check" for tool in tools):
            return None

    doctor_result = await session.call_tool(
        "doctor_check",
        read_timeout_seconds=read_timeout,
    )
    if doctor_result.isError:
        raise RuntimeError("daemon doctor_check probe returned isError=true")
    structured = getattr(doctor_result, "structuredContent", None)
    return structured if isinstance(structured, dict) else None


def run_login() -> None:
    try:
        asyncio.run(interactive_login())
    except KeyboardInterrupt:
        print("\nLogin cancelled.")
        sys.exit(1)
    except Exception as e:
        print(f"Login failed: {e}", file=sys.stderr)
        sys.exit(1)


def run_health() -> None:
    try:
        report = asyncio.run(get_health_report())
        print(json.dumps(report, indent=2, ensure_ascii=False))
        if (
            not report.get("connected", False)
            or not report.get("authorized", False)
            or report.get("error")
        ):
            sys.exit(1)
    except KeyboardInterrupt:
        print("\nHealth check cancelled.", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Health check failed: {e}", file=sys.stderr)
        sys.exit(1)


def run_doctor() -> None:
    try:
        report = asyncio.run(get_doctor_report())
        print(json.dumps(report, indent=2, ensure_ascii=False))
        if report.get("status") != "ok":
            sys.exit(1)
    except KeyboardInterrupt:
        print("\nDoctor check cancelled.", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Doctor check failed: {e}", file=sys.stderr)
        sys.exit(1)
