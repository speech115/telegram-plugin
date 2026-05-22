"""Small in-process operation scheduler for shared Telethon clients."""

from __future__ import annotations

import asyncio
import errno
import math
import time
from collections import OrderedDict, deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, TypeVar

from telethon.errors import FloodWaitError

from .errors import ToolContractError

T = TypeVar("T")

_NETWORK_ERRNOS = {
    errno.ECONNABORTED,
    errno.ECONNREFUSED,
    errno.ECONNRESET,
    errno.EHOSTDOWN,
    errno.EHOSTUNREACH,
    errno.ENETDOWN,
    errno.ENETRESET,
    errno.ENETUNREACH,
    errno.EPIPE,
    errno.ETIMEDOUT,
}
_LOCAL_INPUT_OS_ERRORS = (
    FileNotFoundError,
    IsADirectoryError,
    NotADirectoryError,
    PermissionError,
)


@dataclass
class _CircuitBreakerState:
    error_class: str
    error_code: str
    consecutive_failures: int = 0
    opened_until: float | None = None
    opened_count: int = 0
    last_opened_at: float | None = None
    last_error: str | None = None


@dataclass
class _OperationLabelStats:
    count: int = 0
    succeeded: int = 0
    failed: int = 0
    timed_out: int = 0
    rate_limited: int = 0
    total_queue_wait_ms: float = 0.0
    total_duration_ms: float = 0.0
    max_queue_wait_ms: float = 0.0
    max_duration_ms: float = 0.0
    durations_ms: deque[float] = field(default_factory=lambda: deque(maxlen=128))
    queue_waits_ms: deque[float] = field(default_factory=lambda: deque(maxlen=128))
    last_error: str | None = None


@dataclass
class _OperationLane:
    limit: int
    semaphore: asyncio.Semaphore
    queued: int = 0
    active: int = 0
    completed: int = 0
    failed: int = 0
    timed_out: int = 0
    rate_limited: int = 0
    last_label: str | None = None
    last_started_at: float | None = None
    last_finished_at: float | None = None
    last_error: str | None = None
    last_flood_wait_seconds: int | None = None
    label_stats: OrderedDict[str, _OperationLabelStats] = field(
        default_factory=OrderedDict
    )
    recent_events: deque[dict[str, Any]] = field(default_factory=deque)
    circuit_breakers: dict[str, _CircuitBreakerState] = field(default_factory=dict)


class TelegramOperationScheduler:
    """Bound concurrent Telethon work by operation class and expose bounded metrics."""

    def __init__(
        self,
        *,
        read_concurrency: int,
        write_concurrency: int,
        media_concurrency: int,
        transcribe_concurrency: int,
        enrich_concurrency: int = 4,
        label_limit: int = 64,
        event_limit: int = 100,
        circuit_breaker_enabled: bool = True,
        circuit_breaker_failure_threshold: int = 3,
        circuit_breaker_recovery_seconds: float = 30.0,
    ) -> None:
        self._label_limit = max(1, int(label_limit))
        self._event_limit = max(1, int(event_limit))
        self._circuit_breaker_enabled = bool(circuit_breaker_enabled)
        self._circuit_breaker_failure_threshold = max(
            1,
            int(circuit_breaker_failure_threshold),
        )
        self._circuit_breaker_recovery_seconds = max(
            1.0,
            float(circuit_breaker_recovery_seconds),
        )
        self._lanes: dict[str, _OperationLane] = {
            "read": self._lane(read_concurrency),
            "write": self._lane(write_concurrency),
            "media": self._lane(media_concurrency),
            "transcribe": self._lane(transcribe_concurrency),
            "enrich": self._lane(enrich_concurrency),
        }

    @staticmethod
    def _lane(limit: int) -> _OperationLane:
        try:
            normalized = max(1, int(limit))
        except (TypeError, ValueError):
            normalized = 1
        return _OperationLane(
            limit=normalized,
            semaphore=asyncio.Semaphore(normalized),
        )

    async def run(
        self,
        operation: str,
        label: str,
        timeout_seconds: float,
        factory: Callable[[], Awaitable[T]],
    ) -> T:
        if operation not in self._lanes:
            raise ValueError(f"Unknown Telegram operation lane: {operation}")

        lane = self._lanes[operation]
        label_stats = self._label_stats(lane, label)
        self._raise_if_circuit_open(lane, label, label_stats)
        try:
            timeout = float(timeout_seconds)
        except (TypeError, ValueError):
            timeout = 0.0

        lane.queued += 1
        queued_at = time.perf_counter()
        started_at: float | None = None
        queue_wait_ms = 0.0
        acquired = False

        async def _execute() -> T:
            nonlocal acquired, queue_wait_ms, started_at
            await lane.semaphore.acquire()
            acquired = True
            started_at = time.perf_counter()
            queue_wait_ms = (started_at - queued_at) * 1000
            lane.queued -= 1
            lane.active += 1
            lane.last_label = label
            lane.last_started_at = time.time()
            try:
                return await factory()
            finally:
                lane.active -= 1
                lane.last_finished_at = time.time()
                lane.semaphore.release()

        try:
            if timeout <= 0:
                result = await _execute()
            else:
                async with asyncio.timeout(timeout):
                    result = await _execute()
            duration_ms = self._duration_ms(started_at)
            lane.completed += 1
            lane.last_error = None
            self._reset_circuit_breakers(lane)
            self._record_event(
                lane,
                label_stats,
                label=label,
                status="success",
                queue_wait_ms=queue_wait_ms,
                duration_ms=duration_ms,
            )
            return result
        except FloodWaitError as exc:
            seconds = int(getattr(exc, "seconds", 0) or 0)
            lane.failed += 1
            lane.rate_limited += 1
            lane.last_flood_wait_seconds = seconds
            lane.last_error = f"FloodWaitError: {seconds}s"
            self._record_circuit_breaker_failure(
                lane,
                "flood_wait",
                "rate_limited",
                error=lane.last_error,
                retry_after_seconds=seconds,
            )
            self._record_event(
                lane,
                label_stats,
                label=label,
                status="rate_limited",
                queue_wait_ms=queue_wait_ms,
                duration_ms=self._duration_ms(started_at),
                error=lane.last_error,
            )
            raise ToolContractError(
                "rate_limited",
                f"Telegram rate limit: retry after {seconds}s.",
            ) from None
        except TimeoutError as exc:
            lane.failed += 1
            lane.timed_out += 1
            lane.last_label = label
            lane.last_error = f"TimeoutError: {timeout:g}s"
            self._record_event(
                lane,
                label_stats,
                label=label,
                status="timeout",
                queue_wait_ms=queue_wait_ms,
                duration_ms=self._duration_ms(started_at),
                error=lane.last_error,
            )
            raise ToolContractError(
                "operation_timeout",
                f"{label} timed out after {timeout:g}s.",
            ) from exc
        except Exception as exc:
            lane.failed += 1
            lane.last_error = f"{type(exc).__name__}: {exc}"
            breaker_error_class = self._classify_circuit_breaker_error(exc)
            if breaker_error_class is not None:
                self._record_circuit_breaker_failure(
                    lane,
                    breaker_error_class,
                    "circuit_open",
                    error=lane.last_error,
                )
            self._record_event(
                lane,
                label_stats,
                label=label,
                status="error",
                queue_wait_ms=queue_wait_ms,
                duration_ms=self._duration_ms(started_at),
                error=lane.last_error,
            )
            raise
        finally:
            if not acquired:
                lane.queued -= 1

    def _raise_if_circuit_open(
        self,
        lane: _OperationLane,
        label: str,
        label_stats: _OperationLabelStats,
    ) -> None:
        if not self._circuit_breaker_enabled:
            return

        now = time.time()
        for error_class, state in lane.circuit_breakers.items():
            if state.opened_until is None:
                continue
            if state.opened_until <= now:
                state.opened_until = None
                state.consecutive_failures = 0
                continue

            retry_after_seconds = max(1, math.ceil(state.opened_until - now))
            lane.failed += 1
            lane.last_label = label
            lane.last_error = (
                f"CircuitOpen: {error_class} retry_after={retry_after_seconds}s"
            )
            self._record_event(
                lane,
                label_stats,
                label=label,
                status="circuit_open",
                queue_wait_ms=0.0,
                duration_ms=0.0,
                error=lane.last_error,
            )
            raise ToolContractError(
                state.error_code,
                (
                    f"Telegram {error_class} circuit is open for this lane; "
                    f"retry after {retry_after_seconds}s."
                ),
            )

    def _reset_circuit_breakers(self, lane: _OperationLane) -> None:
        if not self._circuit_breaker_enabled:
            return
        for state in lane.circuit_breakers.values():
            state.consecutive_failures = 0
            if state.opened_until is not None and state.opened_until <= time.time():
                state.opened_until = None

    def _record_circuit_breaker_failure(
        self,
        lane: _OperationLane,
        error_class: str,
        error_code: str,
        *,
        error: str,
        retry_after_seconds: int | None = None,
    ) -> None:
        if not self._circuit_breaker_enabled:
            return

        state = lane.circuit_breakers.get(error_class)
        if state is None:
            state = _CircuitBreakerState(
                error_class=error_class,
                error_code=error_code,
            )
            lane.circuit_breakers[error_class] = state
        state.consecutive_failures += 1
        state.last_error = error

        should_open = retry_after_seconds is not None
        should_open = (
            should_open
            or state.consecutive_failures >= self._circuit_breaker_failure_threshold
        )
        if not should_open:
            return

        recovery_seconds = (
            max(1, int(retry_after_seconds))
            if retry_after_seconds is not None
            else self._circuit_breaker_recovery_seconds
        )
        state.opened_until = time.time() + recovery_seconds
        state.opened_count += 1
        state.last_opened_at = time.time()

    @staticmethod
    def _classify_circuit_breaker_error(exc: Exception) -> str | None:
        if isinstance(exc, ToolContractError):
            if exc.code == "rate_limited":
                return "flood_wait"
            return None
        if isinstance(exc, ConnectionError):
            return "transport"
        if isinstance(exc, _LOCAL_INPUT_OS_ERRORS):
            return None
        if isinstance(exc, OSError):
            if getattr(exc, "errno", None) in _NETWORK_ERRNOS:
                return "transport"
            name = type(exc).__name__.lower()
            if name in {"gaierror", "sslerror"}:
                return "transport"
            return None
        name = type(exc).__name__.lower()
        if "auth" in name or "unauthorized" in name:
            return "auth"
        return None

    def _label_stats(
        self,
        lane: _OperationLane,
        label: str,
    ) -> _OperationLabelStats:
        stats = lane.label_stats.get(label)
        if stats is not None:
            lane.label_stats.move_to_end(label)
            return stats
        while len(lane.label_stats) >= self._label_limit:
            lane.label_stats.popitem(last=False)
        stats = _OperationLabelStats()
        lane.label_stats[label] = stats
        return stats

    @staticmethod
    def _duration_ms(started_at: float | None) -> float:
        if started_at is None:
            return 0.0
        return (time.perf_counter() - started_at) * 1000

    def _record_event(
        self,
        lane: _OperationLane,
        stats: _OperationLabelStats,
        *,
        label: str,
        status: str,
        queue_wait_ms: float,
        duration_ms: float,
        error: str | None = None,
    ) -> None:
        stats.count += 1
        stats.total_queue_wait_ms += queue_wait_ms
        stats.total_duration_ms += duration_ms
        stats.max_queue_wait_ms = max(stats.max_queue_wait_ms, queue_wait_ms)
        stats.max_duration_ms = max(stats.max_duration_ms, duration_ms)
        stats.queue_waits_ms.append(queue_wait_ms)
        stats.durations_ms.append(duration_ms)
        stats.last_error = error

        if status == "success":
            stats.succeeded += 1
        else:
            stats.failed += 1
            if status == "timeout":
                stats.timed_out += 1
            elif status == "rate_limited":
                stats.rate_limited += 1

        lane.recent_events.append(
            {
                "label": label,
                "status": status,
                "queue_wait_ms": round(queue_wait_ms, 3),
                "duration_ms": round(duration_ms, 3),
                "error": error,
                "finished_at": time.time(),
            }
        )
        while len(lane.recent_events) > self._event_limit:
            lane.recent_events.popleft()

    @staticmethod
    def _percentile(values: deque[float], percentile: float) -> float | None:
        if not values:
            return None
        ordered = sorted(values)
        index = round((percentile / 100) * (len(ordered) - 1))
        index = max(0, min(len(ordered) - 1, index))
        return round(ordered[index], 3)

    def _label_snapshot(self, stats: _OperationLabelStats) -> dict[str, Any]:
        return {
            "count": stats.count,
            "succeeded": stats.succeeded,
            "failed": stats.failed,
            "timed_out": stats.timed_out,
            "rate_limited": stats.rate_limited,
            "avg_queue_wait_ms": (
                round(stats.total_queue_wait_ms / stats.count, 3)
                if stats.count
                else 0.0
            ),
            "max_queue_wait_ms": round(stats.max_queue_wait_ms, 3),
            "avg_duration_ms": (
                round(stats.total_duration_ms / stats.count, 3)
                if stats.count
                else 0.0
            ),
            "max_duration_ms": round(stats.max_duration_ms, 3),
            "p50_duration_ms": self._percentile(stats.durations_ms, 50),
            "p95_duration_ms": self._percentile(stats.durations_ms, 95),
            "p99_duration_ms": self._percentile(stats.durations_ms, 99),
            "last_error": stats.last_error,
        }

    def _circuit_breaker_snapshot(
        self,
        state: _CircuitBreakerState,
    ) -> dict[str, Any]:
        retry_after_seconds = None
        if state.opened_until is not None:
            retry_after_seconds = max(0, math.ceil(state.opened_until - time.time()))
        return {
            "error_class": state.error_class,
            "error_code": state.error_code,
            "state": (
                "open"
                if state.opened_until is not None
                and state.opened_until > time.time()
                else "closed"
            ),
            "consecutive_failures": state.consecutive_failures,
            "opened_count": state.opened_count,
            "last_opened_at": state.last_opened_at,
            "retry_after_seconds": retry_after_seconds,
            "last_error": state.last_error,
        }

    def snapshot(self) -> dict[str, dict[str, Any]]:
        return {
            name: {
                "limit": lane.limit,
                "queued": lane.queued,
                "active": lane.active,
                "completed": lane.completed,
                "failed": lane.failed,
                "timed_out": lane.timed_out,
                "rate_limited": lane.rate_limited,
                "last_label": lane.last_label,
                "last_started_at": lane.last_started_at,
                "last_finished_at": lane.last_finished_at,
                "last_error": lane.last_error,
                "last_flood_wait_seconds": lane.last_flood_wait_seconds,
                "labels": {
                    label: self._label_snapshot(stats)
                    for label, stats in lane.label_stats.items()
                },
                "recent_events": list(lane.recent_events),
                "circuit_breakers": {
                    error_class: self._circuit_breaker_snapshot(state)
                    for error_class, state in lane.circuit_breakers.items()
                },
            }
            for name, lane in self._lanes.items()
        }
