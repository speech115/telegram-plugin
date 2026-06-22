"""Detect explore-before-read agent patterns (doctor/get_me before first live read)."""

from __future__ import annotations

import threading
import time

_IDLE_RESET_SECONDS = 300.0

_LOCK = threading.Lock()
_activity_started_at: float | None = None
_first_read_recorded = False
_explore_calls_before_read = 0

SUCCESSFUL_READ_TOOLS = frozenset(
    {
        "telegram_read",
        "collect_dialog_context",
        "collect_context",
        "telegram_search",
        "read_today_dialog",
        "read_recent_dialog",
        "search_dialog_messages",
    }
)

EXPLORE_BEFORE_READ_TOOLS = frozenset(
    {
        "doctor_check",
        "get_me",
    }
)


def reset_agent_preflight_state_for_tests() -> None:
    global _activity_started_at, _first_read_recorded, _explore_calls_before_read
    with _LOCK:
        _activity_started_at = None
        _first_read_recorded = False
        _explore_calls_before_read = 0


def _maybe_reset_idle(now: float) -> None:
    global _activity_started_at, _first_read_recorded, _explore_calls_before_read  # noqa: PLW0603
    if _activity_started_at is None:
        _activity_started_at = now
        _first_read_recorded = False
        _explore_calls_before_read = 0
        return
    if now - _activity_started_at > _IDLE_RESET_SECONDS:
        _activity_started_at = now
        _first_read_recorded = False
        _explore_calls_before_read = 0


def observe_tool_call(
    *,
    tool: str,
    status: str,
    source: str = "mcp_tool",
    traffic_class: str = "agent",
) -> None:
    """Record preflight violations and time-to-first-read for MCP tools."""
    global _first_read_recorded, _explore_calls_before_read

    from .telemetry import record_telemetry

    normalized = tool.strip()
    now = time.monotonic()
    with _LOCK:
        _maybe_reset_idle(now)
        started_at = _activity_started_at or now

        if normalized in SUCCESSFUL_READ_TOOLS and status == "ok":
            if not _first_read_recorded:
                record_telemetry(
                    "seconds_to_first_read",
                    seconds=round(now - started_at, 3),
                    tool=normalized,
                    source=source,
                    explore_calls_before_read=_explore_calls_before_read,
                )
                _first_read_recorded = True
            return

        if not _first_read_recorded and normalized in EXPLORE_BEFORE_READ_TOOLS:
            _explore_calls_before_read += 1
            record_telemetry(
                "preflight_violation",
                tool=normalized,
                status=status,
                source=source,
                traffic_class=traffic_class,
                explore_calls_before_read=_explore_calls_before_read,
            )


def observe_fast_read(*, tool: str, status: str, source: str, duration_ms: float | None = None) -> None:
    """CLI fast-read path: counts as first successful read for the activity window."""
    global _first_read_recorded

    from .telemetry import record_telemetry

    if status != "ok":
        return
    now = time.monotonic()
    with _LOCK:
        _maybe_reset_idle(now)
        started_at = _activity_started_at or now
        if not _first_read_recorded:
            seconds = round((duration_ms or 0) / 1000.0, 3) if duration_ms else round(now - started_at, 3)
            record_telemetry(
                "seconds_to_first_read",
                seconds=seconds,
                tool=tool,
                source=source,
                explore_calls_before_read=_explore_calls_before_read,
            )
            _first_read_recorded = True
