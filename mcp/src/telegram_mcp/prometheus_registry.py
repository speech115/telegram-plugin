"""In-process Prometheus text metrics for Telegram MCP telemetry."""

from __future__ import annotations

import threading
from typing import Any

_DEFAULT_BUCKETS_MS = (25, 50, 100, 250, 500, 1000, 2500, 5000, 10000)


class PrometheusRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: dict[tuple[str, tuple[tuple[str, str], ...]], float] = {}
        self._histograms: dict[str, dict[tuple[tuple[str, str], ...], list[int]]] = {}

    def observe_tool_call(
        self,
        *,
        tool: str,
        status: str,
        duration_ms: float | None,
        source: str = "mcp_tool",
    ) -> None:
        labels = (("tool", tool), ("status", status), ("source", source))
        self._inc("telegram_mcp_tool_calls_total", labels)
        if duration_ms is not None:
            self._observe_histogram(
                "telegram_mcp_tool_duration_ms",
                (("tool", tool), ("source", source)),
                float(duration_ms),
            )

    def observe_event(self, event: str, **labels: str) -> None:
        normalized = (("event", event), *tuple(sorted((k, v) for k, v in labels.items() if v)))
        self._inc("telegram_mcp_events_total", normalized)

    def observe_cache(self, *, kind: str, outcome: str) -> None:
        self._inc(
            "telegram_mcp_cache_access_total",
            (("cache_kind", kind), ("outcome", outcome)),
        )

    def observe_write_operation(
        self,
        *,
        operation: str,
        status: str,
        duration_ms: float | None,
        source: str = "mcp_server",
    ) -> None:
        labels = (("operation", operation), ("status", status), ("source", source))
        self._inc("telegram_mcp_write_operations_total", labels)
        if duration_ms is not None:
            self._observe_histogram(
                "telegram_mcp_write_duration_ms",
                (("operation", operation), ("source", source)),
                float(duration_ms),
            )

    def set_runtime_gauge(self, name: str, value: float) -> None:
        key = (("gauge", name),)
        with self._lock:
            self._counters[("telegram_mcp_runtime_gauge", key)] = float(value)

    def _inc(self, metric: str, labels: tuple[tuple[str, str], ...]) -> None:
        with self._lock:
            key = (metric, labels)
            self._counters[key] = self._counters.get(key, 0.0) + 1.0

    def _observe_histogram(
        self,
        metric: str,
        labels: tuple[tuple[str, str], ...],
        value: float,
    ) -> None:
        with self._lock:
            bucket_store = self._histograms.setdefault(metric, {})
            counts = bucket_store.setdefault(labels, [0] * (len(_DEFAULT_BUCKETS_MS) + 1))
            for index, bound in enumerate(_DEFAULT_BUCKETS_MS):
                if value <= bound:
                    for bucket_index in range(index, len(_DEFAULT_BUCKETS_MS)):
                        counts[bucket_index] += 1
                    counts[-1] += 1
                    break
            else:
                counts[-1] += 1
            bucket_store[labels] = counts

    def render(self) -> str:
        lines: list[str] = []
        with self._lock:
            counter_metrics = sorted({key[0] for key in self._counters})
            for metric in counter_metrics:
                lines.append(f"# TYPE {metric} counter")
                for (name, labels), value in sorted(self._counters.items()):
                    if name != metric:
                        continue
                    lines.append(f"{name}{_format_labels(labels)} {value}")

            for metric, label_map in sorted(self._histograms.items()):
                lines.append(f"# TYPE {metric} histogram")
                for labels, counts in sorted(label_map.items()):
                    for index, bound in enumerate(_DEFAULT_BUCKETS_MS):
                        bucket_labels = (("le", str(bound)), *labels)
                        lines.append(
                            f"{metric}_bucket{_format_labels(bucket_labels)} {counts[index]}"
                        )
                    inf_labels = (("le", "+Inf"), *labels)
                    label_text = _format_labels(labels)
                    lines.append(f"{metric}_bucket{_format_labels(inf_labels)} {counts[-1]}")
                    lines.append(f"{metric}_count{label_text} {counts[-1]}")
        return "\n".join(lines) + "\n"


_registry: PrometheusRegistry | None = None
_registry_lock = threading.Lock()


def get_prometheus_registry() -> PrometheusRegistry:
    global _registry
    with _registry_lock:
        if _registry is None:
            _registry = PrometheusRegistry()
        return _registry


def reset_prometheus_registry_for_tests() -> None:
    global _registry
    with _registry_lock:
        _registry = None


def record_prometheus_from_event(event: str, fields: dict[str, Any]) -> None:
    registry = get_prometheus_registry()
    source = str(fields.get("source", "unknown"))
    registry.observe_event(event, source=source)

    if event == "tool_call":
        tool = str(fields.get("tool", "unknown"))
        status = str(fields.get("status", "unknown"))
        duration = fields.get("duration_ms")
        duration_ms = float(duration) if isinstance(duration, int | float) else None
        registry.observe_tool_call(
            tool=tool,
            status=status,
            duration_ms=duration_ms,
            source=source,
        )
        if fields.get("result_cache_hit") is True:
            registry.observe_cache(kind="dialog_read", outcome="hit")
        elif fields.get("result_cache_hit") is False:
            registry.observe_cache(kind="dialog_read", outcome="miss")
    elif event == "cache_access":
        registry.observe_cache(
            kind=str(fields.get("cache_kind", "other")),
            outcome=str(fields.get("outcome", "unknown")),
        )
    elif event == "write_operation":
        duration = fields.get("duration_ms")
        duration_ms = float(duration) if isinstance(duration, int | float) else None
        registry.observe_write_operation(
            operation=str(fields.get("operation") or fields.get("audit_event") or "unknown"),
            status=str(fields.get("status", "unknown")),
            duration_ms=duration_ms,
            source=source,
        )
    elif event == "fast_read":
        duration = fields.get("duration_ms")
        if isinstance(duration, int | float):
            registry.observe_tool_call(
                tool="fast_read",
                status=str(fields.get("status", "ok")),
                duration_ms=float(duration),
                source="fast_read_cli",
            )
    elif event == "preflight_violation":
        registry.observe_event(
            "preflight_violation",
            tool=str(fields.get("tool", "unknown")),
            source=source,
            traffic_class=str(fields.get("traffic_class", "agent")),
        )
    elif event == "seconds_to_first_read":
        seconds = fields.get("seconds")
        if isinstance(seconds, int | float):
            registry.set_runtime_gauge("agent_seconds_to_first_read", float(seconds))
        registry.observe_event(
            "seconds_to_first_read",
            tool=str(fields.get("tool", "unknown")),
            source=source,
        )


def _format_labels(labels: tuple[tuple[str, str], ...]) -> str:
    if not labels:
        return ""
    inner = ",".join(f'{key}="{_escape(value)}"' for key, value in labels)
    return "{" + inner + "}"


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')
