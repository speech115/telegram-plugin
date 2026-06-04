from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from .paths import POLICY_DIR, TELECRAWL_DEFAULT_DB
from .util import load_json, status_from_findings

TELECRAWL_POLICY_PATH = POLICY_DIR / "telecrawl.json"

DEFAULT_NON_RETRYABLE_TELECRAWL_ERRORS = frozenset(
    {
        "ChannelPrivateError",
        "ChatAdminRequiredError",
        "UserBannedInChannelError",
        "UserNotParticipantError",
        "ChannelInvalidError",
        "InviteHashExpiredError",
        "InviteHashInvalidError",
    }
)


@lru_cache(maxsize=4)
def load_telecrawl_policy(path: str = str(TELECRAWL_POLICY_PATH)) -> dict[str, Any]:
    return load_json(Path(path)) or {}


def clear_policy_cache() -> None:
    load_telecrawl_policy.cache_clear()


def non_retryable_error_types(policy: dict[str, Any] | None = None) -> set[str]:
    payload = policy if policy is not None else load_telecrawl_policy()
    configured = payload.get("non_retryable_error_types")
    if not isinstance(configured, list):
        return set(DEFAULT_NON_RETRYABLE_TELECRAWL_ERRORS)
    return {item for item in configured if isinstance(item, str) and item}


def manifest_path(db_path: Path) -> Path:
    return db_path.with_name(f"{db_path.name}.manifest.json")


def import_gaps(
    db_path: Path | None = None,
    *,
    non_retryable_error_types: set[str] | None = None,
) -> dict[str, Any]:
    db_path = db_path or TELECRAWL_DEFAULT_DB
    terminal_types = non_retryable_error_types or set(DEFAULT_NON_RETRYABLE_TELECRAWL_ERRORS)
    empty = {
        "has_known_gaps": False,
        "has_retryable_gaps": False,
        "has_terminal_gaps": False,
        "errors": 0,
        "retryable_errors": 0,
        "terminal_errors": 0,
        "error_chats": 0,
        "error_summary": [],
        "retryable_error_summary": [],
        "terminal_error_summary": [],
        "non_retryable_error_types": sorted(terminal_types),
    }
    if not db_path.exists():
        return empty
    try:
        with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
            tables = {
                row[0]
                for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            }
            if "import_errors" not in tables:
                return empty
            summary = [
                {"error_type": row[0], "chats": int(row[1] or 0), "attempts": int(row[2] or 0)}
                for row in conn.execute(
                    "SELECT error_type, COUNT(DISTINCT chat_jid) AS chats, COUNT(*) AS attempts "
                    "FROM import_errors GROUP BY error_type ORDER BY attempts DESC"
                ).fetchall()
            ]
            retryable_summary = [row for row in summary if row["error_type"] not in terminal_types]
            terminal_summary = [row for row in summary if row["error_type"] in terminal_types]
            row = conn.execute(
                "SELECT COUNT(*) AS errors, COUNT(DISTINCT chat_jid) AS error_chats FROM import_errors"
            ).fetchone()
    except sqlite3.Error as exc:
        return {
            **empty,
            "has_known_gaps": True,
            "has_retryable_gaps": True,
            "errors": None,
            "retryable_errors": None,
            "terminal_errors": None,
            "error_chats": None,
            "error_summary": [{"error_type": "sqlite_error", "chats": None, "attempts": None}],
            "retryable_error_summary": [{"error_type": "sqlite_error", "chats": None, "attempts": None}],
            "read_error": str(exc),
        }
    total_errors = int(row[0] or 0) if row else 0
    terminal_errors = sum(int(item["attempts"] or 0) for item in terminal_summary)
    retryable_errors = total_errors - terminal_errors
    return {
        "has_known_gaps": bool(total_errors),
        "has_retryable_gaps": retryable_errors > 0,
        "has_terminal_gaps": terminal_errors > 0,
        "errors": total_errors,
        "retryable_errors": retryable_errors,
        "terminal_errors": terminal_errors,
        "error_chats": int(row[1] or 0) if row else 0,
        "error_summary": summary,
        "retryable_error_summary": retryable_summary,
        "terminal_error_summary": terminal_summary,
        "non_retryable_error_types": sorted(terminal_types),
        "retry_policy": {
            "retry_only_when_has_retryable_gaps": True,
            "do_not_retry_terminal_gaps": True,
        },
    }


def default_archive_status(
    db_path: Path | None = None,
    *,
    non_retryable_error_types: set[str] | None = None,
) -> dict[str, Any]:
    db_path = db_path or TELECRAWL_DEFAULT_DB
    manifest = load_json(manifest_path(db_path)) or {}
    import_state = manifest.get("import") if isinstance(manifest.get("import"), dict) else {}
    counts = manifest.get("counts") if isinstance(manifest.get("counts"), dict) else {}
    gaps = import_gaps(db_path, non_retryable_error_types=non_retryable_error_types)
    manifest_status = manifest.get("manifest_status")
    coverage_claim = manifest.get("coverage_claim", "unknown_archive_snapshot")
    if gaps.get("has_known_gaps"):
        coverage_claim = "partial_archive_snapshot_with_known_gaps"
    return {
        "ok": True,
        "source": "telecrawl",
        "source_kind": manifest.get("source_kind", "archive_snapshot"),
        "read_strategy": "manifest_plus_import_errors",
        "coverage_claim": coverage_claim,
        "manifest_coverage_claim": manifest.get("coverage_claim"),
        "manifest_status": manifest_status,
        "archive_ready": db_path.exists() and manifest_status == "complete",
        "import_gaps": gaps,
        "last_complete_import_at": import_state.get("last_complete_import_at"),
        "status": {
            "chats": counts.get("chats"),
            "messages": counts.get("messages"),
            "media_messages": counts.get("media_messages"),
            "oldest_message": counts.get("oldest_message"),
            "newest_message": counts.get("newest_message"),
        },
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }


def known_gaps_findings(
    policy: dict[str, Any],
    import_gaps: dict[str, Any],
) -> list[dict[str, Any]]:
    if not import_gaps.get("has_known_gaps"):
        return []
    severity = (
        "warn"
        if policy.get("known_gaps_are_blocking_for_archive_search") is False
        else "blocking"
    )
    retryable = import_gaps.get("retryable_error_summary")
    terminal = import_gaps.get("terminal_error_summary")
    retryable_count = len(retryable) if isinstance(retryable, list) else 0
    terminal_count = len(terminal) if isinstance(terminal, list) else 0
    expected_ids = policy.get("expected_doctor_warning_ids")
    expected_gap_warning = (
        isinstance(expected_ids, list) and "telecrawl_known_gaps" in expected_ids and severity == "warn"
    )
    return [
        {
            "id": "telecrawl_known_gaps",
            "severity": severity,
            "message": (
                "Telecrawl default archive has known import gaps "
                f"({retryable_count} retryable, {terminal_count} terminal); "
                "not a control-plane release blocker."
                if expected_gap_warning
                else "Telecrawl default archive has known import gaps."
            ),
            "summary": import_gaps.get("error_summary"),
            "retryable_summary": retryable,
            "terminal_summary": terminal,
            "retry_policy": import_gaps.get("retry_policy"),
            "expected_operational_warning": expected_gap_warning,
            "operator_note": policy.get("known_gaps_operator_note"),
        }
    ]


def gap_policy_summary(policy: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = policy if policy is not None else load_telecrawl_policy()
    return {
        "classification": payload.get("classification"),
        "is_live": payload.get("is_live"),
        "known_gaps_are_blocking_for_archive_search": payload.get("known_gaps_are_blocking_for_archive_search"),
        "known_gaps_are_blocking_for_current_claims": payload.get("known_gaps_are_blocking_for_current_claims"),
        "route_current_latest_today_send_reply_media_to": payload.get("route_current_latest_today_send_reply_media_to"),
        "negative_results_claim": payload.get("negative_results_claim"),
    }


def evaluate_archive_readiness(
    *,
    accounts: dict[str, Any],
    archive_status: dict[str, Any],
    policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = policy if policy is not None else load_telecrawl_policy()
    findings: list[dict[str, Any]] = []
    account_rows = accounts.get("accounts") if isinstance(accounts.get("accounts"), list) else []
    active_incomplete = [
        row
        for row in account_rows
        if row.get("active") and (not row.get("db_exists") or row.get("manifest_stale_or_missing"))
    ]
    if active_incomplete:
        findings.append(
            {
                "id": "telecrawl_active_archives_incomplete",
                "severity": "warn",
                "message": "Telecrawl account catalog contains active accounts with missing or stale archives.",
                "count": len(active_incomplete),
            }
        )
    import_gaps_payload = archive_status.get("import_gaps") if isinstance(archive_status.get("import_gaps"), dict) else {}
    findings.extend(known_gaps_findings(payload, import_gaps_payload))
    if archive_status.get("source_kind") != "archive_snapshot":
        findings.append(
            {
                "id": "telecrawl_source_kind_unexpected",
                "severity": "warn",
                "message": "Telecrawl status did not report archive_snapshot source kind.",
            }
        )
    return {
        "status": status_from_findings(findings),
        "findings": findings,
        "gap_policy": gap_policy_summary(payload),
    }