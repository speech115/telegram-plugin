"""Local JSONL telemetry for Telegram MCP (metrics, latency, cache, tool calls)."""

from __future__ import annotations

import json
import math
import threading
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

_FORBIDDEN_FIELD_MARKERS = (
    "text",
    "message",
    "password",
    "token",
    "session_string",
    "api_hash",
)
_MAX_FIELD_LEN = 200
_MAX_KWARG_KEYS = 12


@dataclass(frozen=True)
class TelemetryPaths:
    log_dir: Path
    legacy_log_path: Path
    stats_path: Path


class TelemetryRecorder:
    def __init__(
        self,
        *,
        enabled: bool,
        log_dir: Path,
        legacy_log_path: Path,
        stats_path: Path,
        stats_flush_seconds: int,
        daily_rotation: bool,
        retention_days: int,
        prometheus_enabled: bool,
        transport: str,
        port: int | None,
    ) -> None:
        self.enabled = enabled
        self.log_dir = log_dir.expanduser()
        self.legacy_log_path = legacy_log_path.expanduser()
        self.daily_dir = self.log_dir / "daily"
        self.stats_path = stats_path.expanduser()
        self.stats_flush_seconds = max(0, int(stats_flush_seconds))
        self.daily_rotation = daily_rotation
        self.retention_days = max(1, int(retention_days))
        self.prometheus_enabled = prometheus_enabled
        self.transport = transport
        self.port = port
        self._lock = threading.Lock()
        self._last_stats_flush = 0.0
        self._migrated_legacy = False

    def _target_log_path(self) -> Path:
        if not self.daily_rotation:
            return self.legacy_log_path
        return self.daily_dir / f"{date.today().isoformat()}.jsonl"

    def _migrate_legacy_file_once(self) -> None:
        if self._migrated_legacy or not self.legacy_log_path.exists():
            self._migrated_legacy = True
            return
        if self.legacy_log_path.is_symlink():
            self._migrated_legacy = True
            return
        try:
            text = self.legacy_log_path.read_text(encoding="utf-8")
        except OSError:
            self._migrated_legacy = True
            return
        if not text.strip():
            self._migrated_legacy = True
            return
        target = self._target_log_path()
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as handle:
            handle.write(text if text.endswith("\n") else text + "\n")
        backup = self.legacy_log_path.with_suffix(".jsonl.pre-rotation.bak")
        self.legacy_log_path.rename(backup)
        self._migrated_legacy = True

    def _refresh_legacy_symlink(self, target: Path) -> None:
        if not self.daily_rotation:
            return
        try:
            self.legacy_log_path.parent.mkdir(parents=True, exist_ok=True)
            if self.legacy_log_path.is_symlink() or self.legacy_log_path.exists():
                self.legacy_log_path.unlink()
            self.legacy_log_path.symlink_to(target)
        except OSError:
            return

    def _prune_old_daily_logs(self) -> None:
        if not self.daily_rotation or not self.daily_dir.exists():
            return
        cutoff_day = date.today() - timedelta(days=self.retention_days)
        for path in self.daily_dir.glob("*.jsonl"):
            try:
                file_day = date.fromisoformat(path.stem)
            except ValueError:
                continue
            if file_day < cutoff_day:
                try:
                    path.unlink()
                except OSError:
                    continue

    def record(self, event: str, **fields: Any) -> None:
        if not self.enabled:
            return
        if "source" not in fields:
            fields = {**fields, "source": _default_source_for_event(event)}
        payload = {
            "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "event": event,
            "transport": self.transport,
        }
        if self.port is not None:
            payload["port"] = self.port
        payload.update(_sanitize_fields(fields))
        try:
            self._migrate_legacy_file_once()
            target = self._target_log_path()
            target.parent.mkdir(parents=True, exist_ok=True)
            line = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
            with self._lock:
                with target.open("a", encoding="utf-8") as handle:
                    handle.write(line + "\n")
                self._refresh_legacy_symlink(target)
                self._prune_old_daily_logs()
            if self.prometheus_enabled:
                from .prometheus_registry import record_prometheus_from_event

                record_prometheus_from_event(event, payload)
        except OSError:
            return

    def maybe_flush_stats(
        self,
        *,
        runtime_stats: dict[str, object] | None,
        scheduler: dict[str, dict[str, object]] | None,
    ) -> None:
        if not self.enabled or self.stats_flush_seconds <= 0:
            return
        now = time.monotonic()
        if now - self._last_stats_flush < self.stats_flush_seconds:
            return
        self._last_stats_flush = now
        snapshot = {
            "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "runtime_stats": runtime_stats or {},
            "scheduler": scheduler or {},
        }
        try:
            self.stats_path.parent.mkdir(parents=True, exist_ok=True)
            self.stats_path.write_text(
                json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            self.record("runtime_stats_snapshot", **(runtime_stats or {}))
        except OSError:
            return


_recorder: TelemetryRecorder | None = None
_recorder_lock = threading.Lock()


def build_recorder_from_settings(settings: Any) -> TelemetryRecorder:
    port = int(settings.mcp_port) if getattr(settings, "mcp_transport", "stdio") != "stdio" else None
    return TelemetryRecorder(
        enabled=bool(getattr(settings, "telemetry_enabled", True)),
        log_dir=Path(getattr(settings, "telemetry_log_dir")),
        legacy_log_path=Path(getattr(settings, "telemetry_log_path")),
        stats_path=Path(getattr(settings, "telemetry_stats_path")),
        stats_flush_seconds=int(getattr(settings, "telemetry_stats_flush_seconds", 60)),
        daily_rotation=bool(getattr(settings, "telemetry_daily_rotation", True)),
        retention_days=int(getattr(settings, "telemetry_retention_days", 30)),
        prometheus_enabled=bool(getattr(settings, "telemetry_prometheus_enabled", True)),
        transport=str(getattr(settings, "mcp_transport", "stdio")),
        port=port,
    )


def _default_source_for_event(event: str) -> str:
    return {
        "tool_call": "mcp_tool",
        "fast_read": "fast_read_cli",
        "read_completed": "mcp_server",
        "cache_access": "mcp_server",
        "write_operation": "mcp_server",
        "mcp_restart": "control_plane",
        "mcp_prewarm": "control_plane",
        "runtime_stats_snapshot": "mcp_server",
        "preflight_violation": "mcp_tool",
        "seconds_to_first_read": "mcp_tool",
        "tg_read_today": "fast_read_cli",
        "tg_read_recent": "fast_read_cli",
        "tg_search": "fast_read_cli",
    }.get(event, "mcp_server")


def get_recorder() -> TelemetryRecorder:
    global _recorder
    with _recorder_lock:
        if _recorder is None:
            from .config import get_settings

            _recorder = build_recorder_from_settings(get_settings())
        return _recorder


def reset_recorder_for_tests() -> None:
    global _recorder
    with _recorder_lock:
        _recorder = None


def record_telemetry(event: str, **fields: Any) -> None:
    try:
        get_recorder().record(event, **fields)
    except Exception:
        return


def maybe_flush_runtime_stats() -> None:
    try:
        from .runtime import shared_mode_enabled

        if not shared_mode_enabled():
            return
        from . import runtime as runtime_module

        wrapper = runtime_module._shared_wrapper
        if wrapper is None:
            return
        get_recorder().maybe_flush_stats(
            runtime_stats=wrapper._runtime_stats_snapshot(),
            scheduler=wrapper._scheduler.snapshot(),
        )
    except Exception:
        return


def telemetry_fields_from_kwargs(kwargs: dict[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key, value in list(kwargs.items())[:_MAX_KWARG_KEYS]:
        lowered = key.lower()
        if any(marker in lowered for marker in _FORBIDDEN_FIELD_MARKERS):
            continue
        safe[f"arg_{key}"] = _sanitize_value(value)
    return safe


def telemetry_fields_from_result(result: Any) -> dict[str, Any]:
    if result is None:
        return {}
    fields: dict[str, Any] = {}
    metric_names = (
        "result_cache_hit",
        "result_cache_age_seconds",
        "result_cache_ttl_seconds",
        "message_count",
        "has_more_before",
        "truncated",
        "data_source",
        "collection_mode",
        "voice_transcription_status",
    )
    if isinstance(result, dict):
        for name in metric_names:
            value = result.get(name)
            if value is not None:
                fields[name] = value
        chat = result.get("chat")
        dialog_ref = chat.get("dialog_ref") if isinstance(chat, dict) else None
    else:
        for name in metric_names:
            if hasattr(result, name):
                value = getattr(result, name)
                if value is not None:
                    fields[name] = value
        chat = getattr(result, "chat", None)
        dialog_ref = getattr(chat, "dialog_ref", None)
    if isinstance(dialog_ref, str) and dialog_ref:
        fields["dialog_ref_prefix"] = dialog_ref.split("/", 1)[0]
    return fields


def _sanitize_fields(fields: dict[str, Any]) -> dict[str, Any]:
    return {key: _sanitize_value(value) for key, value in fields.items() if _safe_key(key)}


def _safe_key(key: str) -> bool:
    lowered = key.lower()
    return not any(marker in lowered for marker in _FORBIDDEN_FIELD_MARKERS)


def _sanitize_value(value: Any) -> Any:
    if value is None or isinstance(value, bool | int | float):
        return value
    if isinstance(value, str):
        return value[:_MAX_FIELD_LEN]
    if isinstance(value, list | tuple):
        return [_sanitize_value(item) for item in list(value)[:8]]
    return str(value)[:_MAX_FIELD_LEN]


def _parse_ts(raw: str) -> datetime | None:
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def resolve_log_sources(log_path: str | Path | None = None, *, log_dir: str | Path | None = None) -> list[Path]:
    if log_dir is not None:
        base = Path(log_dir).expanduser()
        daily = base / "daily"
        if daily.is_dir():
            return sorted(daily.glob("*.jsonl"))
        if base.is_dir():
            return sorted(base.glob("*.jsonl"))
        return []

    path = Path(log_path or Path.home() / "telegram-mcp" / "telemetry.jsonl").expanduser()
    sources: list[Path] = []
    daily_dir = path.parent / "telemetry" / "daily"
    if daily_dir.is_dir():
        sources.extend(sorted(daily_dir.glob("*.jsonl")))
    if path.is_dir():
        sources.extend(sorted(path.glob("daily/*.jsonl")))
        sources.extend(sorted(path.glob("*.jsonl")))
    elif path.exists():
        if path not in sources:
            sources.append(path)
    deduped: list[Path] = []
    seen: set[str] = set()
    for item in sources:
        key = str(item.resolve())
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def summarize_telemetry_log(
    log_path: str | Path | None = None,
    *,
    log_dir: str | Path | None = None,
    window_hours: float = 24.0,
    max_lines: int = 200_000,
) -> dict[str, Any]:
    sources = resolve_log_sources(log_path, log_dir=log_dir)
    if not sources:
        missing = str(log_dir or log_path or Path.home() / "telegram-mcp" / "telemetry.jsonl")
        return {
            "status": "missing",
            "log_path": missing,
            "log_sources": [],
            "window_hours": window_hours,
            "events_in_window": 0,
        }

    cutoff = datetime.now(timezone.utc) - timedelta(hours=window_hours)
    counts: dict[str, int] = {}
    tool_durations: dict[str, list[float]] = {}
    tool_errors_by_tool: dict[str, int] = {}
    tool_error_buckets: dict[tuple[str, str, str, int | str], int] = {}
    write_durations: dict[str, list[float]] = {}
    write_by_operation: dict[str, dict[str, int]] = {}
    write_errors = 0
    cache_hits = 0
    cache_misses = 0
    errors = 0
    events_in_window = 0
    newest_ts: datetime | None = None
    oldest_ts: datetime | None = None

    source_counts: dict[str, int] = {}
    preflight_violations = 0
    synthetic_probe_violations = 0
    first_read_seconds: list[float] = []
    lines_read = 0
    for source_path in sources:
        with source_path.open(encoding="utf-8") as handle:
            for line in handle:
                lines_read += 1
                if lines_read > max_lines:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(event, dict):
                    continue
                ts = _parse_ts(str(event.get("ts", "")))
                if ts is None or ts < cutoff:
                    continue
                events_in_window += 1
                newest_ts = ts if newest_ts is None or ts > newest_ts else newest_ts
                oldest_ts = ts if oldest_ts is None or ts < oldest_ts else oldest_ts

                name = str(event.get("event", "unknown"))
                counts[name] = counts.get(name, 0) + 1
                source = str(event.get("source", "unknown"))
                source_counts[source] = source_counts.get(source, 0) + 1

                if name == "tool_call" and event.get("status") != "ok":
                    errors += 1
                    tool = str(event.get("tool", "unknown"))
                    error_type = str(event.get("error_type") or "unknown")
                    error_code = str(event.get("error_code") or "unknown")
                    port = event.get("port")
                    bucket_port: int | str = port if isinstance(port, int) else "unknown"
                    tool_errors_by_tool[tool] = tool_errors_by_tool.get(tool, 0) + 1
                    bucket = (tool, error_type, error_code, bucket_port)
                    tool_error_buckets[bucket] = tool_error_buckets.get(bucket, 0) + 1
                if event.get("result_cache_hit") is True:
                    cache_hits += 1
                elif event.get("result_cache_hit") is False and name in {
                    "tool_call",
                    "read_completed",
                    "telegram_read_completed",
                }:
                    cache_misses += 1
                if name == "cache_access":
                    if event.get("outcome") == "hit":
                        cache_hits += 1
                    elif event.get("outcome") == "miss":
                        cache_misses += 1

                if name == "tool_call":
                    tool = str(event.get("tool", "unknown"))
                    duration = event.get("duration_ms")
                    if isinstance(duration, int | float):
                        tool_durations.setdefault(tool, []).append(float(duration))
                if name == "write_operation":
                    operation = str(event.get("operation") or event.get("audit_event") or "unknown")
                    status = str(event.get("status") or "unknown")
                    by_status = write_by_operation.setdefault(operation, {"count": 0, "errors": 0})
                    by_status["count"] += 1
                    write_failed = status in {"error", "failed", "timed_out", "timeout", "rate_limited"} or (
                        event.get("error_type") is not None or event.get("error_code") is not None
                    )
                    if write_failed:
                        write_errors += 1
                        by_status["errors"] += 1
                    duration = event.get("duration_ms")
                    if status != "started" and isinstance(duration, int | float):
                        write_durations.setdefault(operation, []).append(float(duration))
                if name == "preflight_violation":
                    if event.get("traffic_class") == "synthetic_probe":
                        synthetic_probe_violations += 1
                    else:
                        preflight_violations += 1
                if name == "seconds_to_first_read":
                    seconds = event.get("seconds")
                    if isinstance(seconds, int | float):
                        first_read_seconds.append(float(seconds))
        if lines_read > max_lines:
            break

    tool_summary: dict[str, Any] = {}
    for tool, durations in sorted(tool_durations.items()):
        durations.sort()
        tool_summary[tool] = {
            "count": len(durations),
            "p50_ms": _percentile(durations, 0.5),
            "p95_ms": _percentile(durations, 0.95),
            "max_ms": round(max(durations), 3) if durations else None,
        }
    write_latency: dict[str, Any] = {}
    for operation, durations in sorted(write_durations.items()):
        durations.sort()
        write_latency[operation] = {
            "count": len(durations),
            "p50_ms": _percentile(durations, 0.5),
            "p95_ms": _percentile(durations, 0.95),
            "max_ms": round(max(durations), 3) if durations else None,
        }
    sorted_error_buckets = [
        {
            "tool": tool,
            "error_type": error_type,
            "error_code": error_code,
            "port": port,
            "count": count,
        }
        for (tool, error_type, error_code, port), count in sorted(
            tool_error_buckets.items(),
            key=lambda item: (-item[1], item[0][0], item[0][1], item[0][2], str(item[0][3])),
        )
    ]

    cache_total = cache_hits + cache_misses
    first_read_seconds.sort()
    agent_preflight: dict[str, Any] = {
        "preflight_violations": preflight_violations,
        "synthetic_probe_violations": synthetic_probe_violations,
    }
    if first_read_seconds:
        agent_preflight["seconds_to_first_read"] = {
            "count": len(first_read_seconds),
            "p50": round(_percentile(first_read_seconds, 0.5), 3),
            "p95": round(_percentile(first_read_seconds, 0.95), 3),
            "max": round(max(first_read_seconds), 3),
        }
    return {
        "status": "ok",
        "log_path": str(sources[-1]),
        "log_sources": [str(item) for item in sources],
        "window_hours": window_hours,
        "events_in_window": events_in_window,
        "lines_read": lines_read,
        "window_start": oldest_ts.isoformat().replace("+00:00", "Z") if oldest_ts else None,
        "window_end": newest_ts.isoformat().replace("+00:00", "Z") if newest_ts else None,
        "event_counts": counts,
        "source_counts": source_counts,
        "tool_latency": tool_summary,
        "cache": {
            "hits": cache_hits,
            "misses": cache_misses,
            "hit_rate": round(cache_hits / cache_total, 4) if cache_total else None,
        },
        "agent_preflight": agent_preflight,
        "tool_errors": errors,
        "tool_errors_by_tool": dict(sorted(tool_errors_by_tool.items())),
        "tool_error_buckets": sorted_error_buckets,
        "write_operations": {
            "count": sum(item["count"] for item in write_by_operation.values()),
            "errors": write_errors,
            "by_operation": dict(sorted(write_by_operation.items())),
            "latency": write_latency,
        },
    }


def _percentile(values: list[float], ratio: float) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return round(values[0], 3)
    index = max(0, min(len(values) - 1, math.ceil(ratio * len(values)) - 1))
    return round(values[index], 3)


def _build_parser():
    import argparse

    parser = argparse.ArgumentParser(description="Telegram MCP local telemetry utilities.")
    parser.add_argument("--summarize", action="store_true")
    parser.add_argument("--log-path", default=None)
    parser.add_argument("--log-dir", default=None)
    parser.add_argument("--window-hours", type=float, default=24.0)
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    import sys

    args = _build_parser().parse_args(argv)
    if not args.summarize:
        args = _build_parser().parse_args(["--summarize", * (argv or sys.argv[1:])])

    if args.log_dir:
        payload = summarize_telemetry_log(log_dir=args.log_dir, window_hours=args.window_hours)
    elif args.log_path:
        payload = summarize_telemetry_log(args.log_path, window_hours=args.window_hours)
    else:
        from .config import get_settings

        settings = get_settings()
        payload = summarize_telemetry_log(
            settings.telemetry_log_path,
            log_dir=settings.telemetry_log_dir,
            window_hours=args.window_hours,
        )
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(payload, ensure_ascii=False))
    return 0 if payload.get("status") in {"ok", "missing"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
