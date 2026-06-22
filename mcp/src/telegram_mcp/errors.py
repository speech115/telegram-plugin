"""Error handling for MCP tools."""

from __future__ import annotations

import functools
import time

import structlog
from telethon.errors import (
    AuthKeyUnregisteredError,
    ChannelPrivateError,
    ChatAdminRequiredError,
    ChatWriteForbiddenError,
    FloodWaitError,
    PeerFloodError,
    SlowModeWaitError,
    UserBannedInChannelError,
    UserDeactivatedBanError,
    UserNotMutualContactError,
    UserPrivacyRestrictedError,
    UsernameInvalidError,
)

log = structlog.get_logger()

class ToolContractError(ValueError):
    """Structured tool-facing error with a stable machine-readable code."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


_FRIENDLY: dict[type, tuple[str, str]] = {
    AuthKeyUnregisteredError: (
        "transport_unavailable",
        "Telegram session expired. Run 'telegram-mcp login' to re-authenticate.",
    ),
    UserDeactivatedBanError: (
        "permission_denied",
        "Telegram account is deactivated or banned.",
    ),
    ChatWriteForbiddenError: (
        "permission_denied",
        "No permission to write in this chat.",
    ),
    ChannelPrivateError: (
        "permission_denied",
        "This channel/group is private or you are not a member.",
    ),
    ChatAdminRequiredError: (
        "permission_denied",
        "Admin rights required for this operation.",
    ),
    UserBannedInChannelError: (
        "permission_denied",
        "You are banned in this channel.",
    ),
    UserNotMutualContactError: (
        "permission_denied",
        "Cannot add user — they are not a mutual contact.",
    ),
    SlowModeWaitError: (
        "rate_limited",
        "Telegram slow mode is active in this chat. Retry later.",
    ),
    PeerFloodError: (
        "rate_limited",
        "Telegram limited this account because it is sending too many peer actions.",
    ),
    UserPrivacyRestrictedError: (
        "permission_denied",
        "The user's privacy settings block this operation.",
    ),
    UsernameInvalidError: (
        "invalid_input",
        "Telegram username is invalid.",
    ),
}

def tool_error_handler(fn):
    """Wrap a tool function with structured error handling and logging."""

    @functools.wraps(fn)
    async def wrapper(*args, **kwargs):
        from .telemetry import (
            maybe_flush_runtime_stats,
            record_telemetry,
            telemetry_fields_from_kwargs,
            telemetry_fields_from_result,
        )

        started = time.perf_counter()
        safe_args = telemetry_fields_from_kwargs(kwargs)
        from .agent_preflight import observe_tool_call

        try:
            result = await fn(*args, **kwargs)
        except ToolContractError as exc:
            observe_tool_call(tool=fn.__name__, status="error", source="mcp_tool")
            duration_ms = round((time.perf_counter() - started) * 1000, 3)
            record_telemetry(
                "tool_call",
                tool=fn.__name__,
                status="error",
                duration_ms=duration_ms,
                source="mcp_tool",
                error_type=type(exc).__name__,
                error_code=exc.code,
                **safe_args,
            )
            log.error("tool_contract_error", tool=fn.__name__, code=exc.code, error=exc.message)
            from .intent_router import format_contract_error

            raise ValueError(format_contract_error(exc)) from None
        except FloodWaitError as exc:
            observe_tool_call(tool=fn.__name__, status="error", source="mcp_tool")
            duration_ms = round((time.perf_counter() - started) * 1000, 3)
            record_telemetry(
                "tool_call",
                tool=fn.__name__,
                status="error",
                duration_ms=duration_ms,
                source="mcp_tool",
                error_type=type(exc).__name__,
                error_code="rate_limited",
                retry_after_seconds=exc.seconds,
                **safe_args,
            )
            log.warning("flood_wait", tool=fn.__name__, seconds=exc.seconds)
            raise ValueError(
                f"rate_limited: Telegram rate limit: retry after {exc.seconds}s."
            ) from None
        except tuple(_FRIENDLY) as exc:
            observe_tool_call(tool=fn.__name__, status="error", source="mcp_tool")
            code, msg = _FRIENDLY.get(type(exc), ("tool_error", str(exc)))
            duration_ms = round((time.perf_counter() - started) * 1000, 3)
            record_telemetry(
                "tool_call",
                tool=fn.__name__,
                status="error",
                duration_ms=duration_ms,
                source="mcp_tool",
                error_type=type(exc).__name__,
                error_code=code,
                **safe_args,
            )
            log.error("tool_error", tool=fn.__name__, code=code, error=msg)
            raise ValueError(f"{code}: {msg}") from None
        except Exception as exc:
            observe_tool_call(tool=fn.__name__, status="error", source="mcp_tool")
            duration_ms = round((time.perf_counter() - started) * 1000, 3)
            record_telemetry(
                "tool_call",
                tool=fn.__name__,
                status="error",
                duration_ms=duration_ms,
                source="mcp_tool",
                error_type=type(exc).__name__,
                **safe_args,
            )
            log.error("tool_unexpected_error", tool=fn.__name__, exc_info=True)
            raise

        duration_ms = round((time.perf_counter() - started) * 1000, 3)
        observe_tool_call(tool=fn.__name__, status="ok", source="mcp_tool")
        record_telemetry(
            "tool_call",
            tool=fn.__name__,
            status="ok",
            duration_ms=duration_ms,
            source="mcp_tool",
            **safe_args,
            **telemetry_fields_from_result(result),
        )
        maybe_flush_runtime_stats()
        return result

    return wrapper
