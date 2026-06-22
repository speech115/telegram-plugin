"""Restart local Telegram MCP HTTP launchd agents after doc or code changes."""

from __future__ import annotations

import os
import subprocess
from dataclasses import asdict, dataclass


DEFAULT_MCP_HTTP_LABELS = (
    "com.sereja.telegram-mcp-http",
    "com.sereja.telegram-mcp-http-pl",
)


@dataclass(frozen=True)
class McpRestartResult:
    status: str
    uid: int
    labels: list[str]
    restarted: list[str]
    failures: list[str]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def restart_mcp_http_daemons(
    *,
    labels: list[str] | None = None,
    uid: int | None = None,
    prewarm: bool = True,
    prewarm_timeout: float = 8.0,
) -> McpRestartResult:
    target_uid = uid if uid is not None else os.getuid()
    target_labels = list(labels or DEFAULT_MCP_HTTP_LABELS)
    restarted: list[str] = []
    failures: list[str] = []

    for label in target_labels:
        target = f"gui/{target_uid}/{label}"
        completed = subprocess.run(
            ["launchctl", "kickstart", "-k", target],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode == 0:
            restarted.append(label)
            continue
        stderr = (completed.stderr or "").strip()
        failures.append(f"{label}: exit {completed.returncode} {stderr}".strip())

    status = "ok" if restarted and not failures else ("partial" if restarted else "fail")
    result = McpRestartResult(
        status=status,
        uid=target_uid,
        labels=target_labels,
        restarted=restarted,
        failures=failures,
    )
    if restarted:
        from .telemetry import record_telemetry

        record_telemetry(
            "mcp_restart",
            status=status,
            restarted_count=len(restarted),
            failure_count=len(failures),
        )
    if prewarm and restarted:
        try:
            from .mcp_prewarm import prewarm_mcp_http

            prewarm_result = prewarm_mcp_http(timeout=prewarm_timeout)
            from .telemetry import record_telemetry

            record_telemetry(
                "mcp_prewarm",
                status=prewarm_result.status,
                attempt_count=len(prewarm_result.attempts),
            )
        except Exception:
            pass
    return result