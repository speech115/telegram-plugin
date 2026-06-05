from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

from .paths import POLICY_DIR
from .util import load_json, status_from_findings

RUNTIME_INVENTORY_PATH = POLICY_DIR / "runtime-inventory.json"


@lru_cache(maxsize=4)
def load_runtime_inventory_policy(path: str = str(RUNTIME_INVENTORY_PATH)) -> dict[str, Any]:
    return load_json(Path(path)) or {}


def clear_policy_cache() -> None:
    load_runtime_inventory_policy.cache_clear()


def _summarize_child(child_id: str, report: dict[str, Any], policy_item: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {"status": report.get("status"), "finding_count": len(report.get("findings", []))}
    if child_id == "launchd":
        jobs = report.get("loaded_jobs") if isinstance(report.get("loaded_jobs"), list) else []
        summary["loaded_job_count"] = len(jobs)
    if child_id == "sessions":
        inner = report.get("summary") if isinstance(report.get("summary"), dict) else {}
        summary.update({key: inner.get(key) for key in ("discovered", "registered", "runtime_allowed")})
    if child_id == "mirror_runtime":
        mirror_summary = report.get("runtime_state_summary")
        if isinstance(mirror_summary, dict):
            for field in policy_item.get("summary_fields", []):
                if isinstance(field, str):
                    summary[field] = mirror_summary.get(field)
    return summary


@dataclass(frozen=True)
class RuntimeSnapshot:
    launchd: dict[str, Any]
    sessions: dict[str, Any]
    mirror_runtime: dict[str, Any]

    @classmethod
    def collect(
        cls,
        *,
        launchd_report: dict[str, Any] | None = None,
        sessions_report: dict[str, Any] | None = None,
        mirror_report: dict[str, Any] | None = None,
        audit_launchd: Callable[[], dict[str, Any]] | None = None,
        audit_sessions: Callable[[], dict[str, Any]] | None = None,
        audit_mirror: Callable[[], dict[str, Any]] | None = None,
    ) -> "RuntimeSnapshot":
        from . import audits

        launchd_fn = audit_launchd or audits.audit_launchd
        sessions_fn = audit_sessions or audits.audit_sessions
        mirror_fn = audit_mirror or audits.audit_mirror
        return cls(
            launchd=launchd_report if launchd_report is not None else launchd_fn(),
            sessions=sessions_report if sessions_report is not None else sessions_fn(),
            mirror_runtime=mirror_report if mirror_report is not None else mirror_fn(),
        )

    def children(self) -> dict[str, dict[str, Any]]:
        return {
            "launchd": self.launchd,
            "sessions": self.sessions,
            "mirror_runtime": self.mirror_runtime,
        }


def audit_runtime_inventory(
    *,
    launchd_report: dict[str, Any] | None = None,
    sessions_report: dict[str, Any] | None = None,
    mirror_report: dict[str, Any] | None = None,
    audit_launchd: Callable[[], dict[str, Any]] | None = None,
    audit_sessions: Callable[[], dict[str, Any]] | None = None,
    audit_mirror: Callable[[], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    snapshot = RuntimeSnapshot.collect(
        launchd_report=launchd_report,
        sessions_report=sessions_report,
        mirror_report=mirror_report,
        audit_launchd=audit_launchd,
        audit_sessions=audit_sessions,
        audit_mirror=audit_mirror,
    )
    policy = load_runtime_inventory_policy()
    aggregates = policy.get("aggregates") if isinstance(policy.get("aggregates"), list) else []
    children = snapshot.children()
    summaries: dict[str, Any] = {}
    findings: list[dict[str, Any]] = []

    for item in aggregates:
        if not isinstance(item, dict):
            continue
        child_id = str(item.get("id") or "")
        report = children.get(child_id)
        if not isinstance(report, dict):
            continue
        summaries[child_id] = _summarize_child(child_id, report, item)
        for finding in report.get("findings", []):
            if not isinstance(finding, dict):
                continue
            enriched = dict(finding)
            enriched.setdefault("component", f"runtime_inventory/{child_id}")
            findings.append(enriched)

    blocking_ids = policy.get("blocking_when_any_fail")
    if isinstance(blocking_ids, list):
        for child_id in blocking_ids:
            if isinstance(child_id, str) and summaries.get(child_id, {}).get("status") == "fail":
                findings.append(
                    {
                        "id": "runtime_inventory_child_failed",
                        "severity": "blocking",
                        "child": child_id,
                        "message": f"Runtime inventory child {child_id} is in fail state.",
                    }
                )

    return {
        "status": status_from_findings(findings),
        "findings": findings,
        "policy_path": str(RUNTIME_INVENTORY_PATH),
        "summary": summaries,
        "children": {
            child_id: {"status": report.get("status")}
            for child_id, report in children.items()
            if isinstance(report, dict)
        },
    }
