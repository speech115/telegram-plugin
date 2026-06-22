from __future__ import annotations

from typing import Any

from .audits import audit_mcp_telemetry
from .paths import MCP_TELEMETRY_STATS
from .util import load_json


def _runtime_lanes() -> dict[str, Any]:
    payload = load_json(MCP_TELEMETRY_STATS)
    if not isinstance(payload, dict):
        return {}
    runtime_stats = payload.get("runtime_stats")
    if not isinstance(runtime_stats, dict):
        return {}
    lanes = runtime_stats.get("lanes")
    if isinstance(lanes, dict):
        return lanes
    return {
        key: value
        for key, value in runtime_stats.items()
        if isinstance(value, dict)
    }


def _add_slow_tools(recommendations: list[dict[str, Any]], telemetry: dict[str, Any]) -> None:
    for row in telemetry.get("top_slow_tools", [])[:5]:
        if not isinstance(row, dict):
            continue
        tool = str(row.get("tool") or "unknown")
        p95 = row.get("p95_ms")
        if "media" in tool or tool in {"send_file", "download_dialog_media", "download_media_batch"}:
            recommendation = (
                "Start with a scoped media manifest and batch downloads; avoid broad media fetches "
                "until selected message ids are known."
            )
        else:
            recommendation = "Start with this path when optimizing latency; it has real recent traffic."
        recommendations.append(
            {
                "kind": "slow_tool",
                "subject": tool,
                "severity": "warn",
                "message": f"{tool} is among the slowest tools in the telemetry window.",
                "p95_ms": p95,
                "max_ms": row.get("max_ms"),
                "recommendation": recommendation,
            }
        )


def _add_error_buckets(recommendations: list[dict[str, Any]], telemetry: dict[str, Any]) -> None:
    grouped: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in telemetry.get("top_tool_error_buckets", []):
        if not isinstance(row, dict):
            continue
        tool = str(row.get("tool") or "unknown")
        error_type = str(row.get("error_type") or "unknown")
        error_code = str(row.get("error_code") or "unknown")
        key = (tool, error_type, error_code)
        item = grouped.setdefault(
            key,
            {
                "tool": tool,
                "error_type": error_type,
                "error_code": error_code,
                "count": 0,
                "ports": set(),
            },
        )
        count = row.get("count")
        if isinstance(count, int | float):
            item["count"] += int(count)
        port = row.get("port")
        if port is not None:
            item["ports"].add(port)

    rows = sorted(
        grouped.values(),
        key=lambda item: (-int(item["count"]), str(item["tool"]), str(item["error_type"])),
    )
    for row in rows[:5]:
        error_type = str(row.get("error_type") or "unknown")
        kind = "floodwait" if error_type in {"FloodWaitError", "PeerFloodError"} else "tool_error"
        recommendations.append(
            {
                "kind": kind,
                "subject": str(row.get("tool") or "unknown"),
                "severity": "warn",
                "message": f"{row.get('tool', 'unknown')} has recent {error_type} errors.",
                "count": row.get("count"),
                "error_type": error_type,
                "error_code": row.get("error_code"),
                "ports": sorted(row.get("ports") or []),
                "recommendation": (
                    "Treat FloodWait as a throughput signal; reduce duplicate reads or improve caching."
                    if kind == "floodwait"
                    else "Inspect the top error bucket before broad refactors."
                ),
            }
        )


def _add_audit_findings(recommendations: list[dict[str, Any]], telemetry: dict[str, Any]) -> None:
    for finding in telemetry.get("findings", []):
        if not isinstance(finding, dict):
            continue
        recommendations.append(
            {
                "kind": "telemetry_finding",
                "subject": finding.get("id"),
                "severity": finding.get("severity", "warn"),
                "message": finding.get("message"),
                "recommendation": "Resolve or intentionally accept this telemetry finding.",
            }
        )


def _add_lane_pressure(recommendations: list[dict[str, Any]]) -> None:
    for lane, stats in _runtime_lanes().items():
        if not isinstance(stats, dict):
            continue
        rate_limited = stats.get("rate_limited")
        queue_wait = stats.get("max_queue_wait_ms")
        if not rate_limited and not queue_wait:
            continue
        recommendations.append(
            {
                "kind": "lane_pressure",
                "subject": str(lane),
                "severity": "warn",
                "message": f"{lane} lane shows queue or rate-limit pressure.",
                "rate_limited": rate_limited,
                "max_queue_wait_ms": queue_wait,
                "p95_duration_ms": stats.get("p95_duration_ms"),
                "recommendation": "Check whether this lane needs batching, caching, or lower concurrent demand.",
            }
        )


def build_insights(*, window_hours: float | None = None) -> dict[str, Any]:
    telemetry = audit_mcp_telemetry(window_hours=window_hours)
    recommendations: list[dict[str, Any]] = []
    _add_slow_tools(recommendations, telemetry)
    _add_error_buckets(recommendations, telemetry)
    _add_audit_findings(recommendations, telemetry)
    _add_lane_pressure(recommendations)
    findings = telemetry.get("findings") if isinstance(telemetry.get("findings"), list) else []
    return {
        "command": "insights",
        "status": telemetry.get("status", "ok"),
        "findings": findings,
        "window_hours": window_hours,
        "events_in_window": telemetry.get("events_in_window"),
        "cache_hit_rate": telemetry.get("cache_hit_rate"),
        "recommendations": recommendations,
        "telemetry_status": telemetry.get("status"),
        "artifacts": telemetry.get("artifacts", {}),
    }
