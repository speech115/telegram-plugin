"""Error handling for MCP tools."""

from __future__ import annotations

import functools

import structlog
from telethon.errors import (
    AuthKeyUnregisteredError,
    ChannelPrivateError,
    ChatAdminRequiredError,
    ChatWriteForbiddenError,
    FloodWaitError,
    UserBannedInChannelError,
    UserDeactivatedBanError,
    UserNotMutualContactError,
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
}

def tool_error_handler(fn):
    """Wrap a tool function with structured error handling and logging."""

    @functools.wraps(fn)
    async def wrapper(*args, **kwargs):
        try:
            return await fn(*args, **kwargs)
        except ToolContractError as exc:
            log.error("tool_contract_error", tool=fn.__name__, code=exc.code, error=exc.message)
            raise ValueError(str(exc)) from None
        except FloodWaitError as exc:
            log.warning("flood_wait", tool=fn.__name__, seconds=exc.seconds)
            raise ValueError(
                f"rate_limited: Telegram rate limit: retry after {exc.seconds}s."
            ) from None
        except tuple(_FRIENDLY) as exc:
            code, msg = _FRIENDLY.get(type(exc), ("tool_error", str(exc)))
            log.error("tool_error", tool=fn.__name__, code=code, error=msg)
            raise ValueError(f"{code}: {msg}") from None
        except Exception:
            log.error("tool_unexpected_error", tool=fn.__name__, exc_info=True)
            raise

    return wrapper
