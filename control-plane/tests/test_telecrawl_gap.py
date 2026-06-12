from __future__ import annotations

import sqlite3
from pathlib import Path

from telegram_control_plane.source_evidence import source_evidence_rules
from telegram_control_plane.telecrawl_gap import (
    gap_policy_summary,
    import_gaps,
    known_gaps_findings,
    load_telecrawl_policy,
    non_retryable_error_types,
)


def test_telecrawl_policy_declares_expected_gap_warning() -> None:
    policy = load_telecrawl_policy()
    assert policy.get("known_gaps_are_blocking_for_archive_search") is False
    assert "telecrawl_known_gaps" in policy.get("expected_doctor_warning_ids", [])
    assert policy.get("source_evidence_owner") == "policy/source-routing.json"
    assert "route_current_latest_today_send_reply_media_to" not in policy
    assert "negative_results_claim" not in policy


def test_import_gaps_split_retryable_and_terminal(tmp_path: Path) -> None:
    db = tmp_path / "telecrawl-fast.db"
    with sqlite3.connect(db) as conn:
        conn.executescript(
            """
            CREATE TABLE import_errors (chat_jid text, error_type text);
            INSERT INTO import_errors VALUES ('1', 'ChannelPrivateError'), ('1', 'ChannelPrivateError');
            INSERT INTO import_errors VALUES ('2', 'TimeoutError');
            """
        )
    gaps = import_gaps(db, non_retryable_error_types={"ChannelPrivateError"})
    assert gaps["errors"] == 3
    assert gaps["retryable_errors"] == 1
    assert gaps["terminal_errors"] == 2
    assert gaps["has_retryable_gaps"] is True
    assert gaps["has_terminal_gaps"] is True


def test_known_gaps_finding_is_operational_warn_by_default() -> None:
    policy = load_telecrawl_policy()
    findings = known_gaps_findings(
        policy,
        {"has_known_gaps": True, "retryable_error_summary": [], "terminal_error_summary": []},
    )
    assert findings[0]["id"] == "telecrawl_known_gaps"
    assert findings[0]["severity"] == "warn"
    assert findings[0]["expected_operational_warning"] is True


def test_non_retryable_error_types_defaults() -> None:
    policy = load_telecrawl_policy()
    types = non_retryable_error_types(policy)
    assert "ChannelPrivateError" in types


def test_gap_policy_summary_gets_shared_claims_from_source_evidence_rules() -> None:
    summary = gap_policy_summary()
    rules = source_evidence_rules()

    assert summary["route_current_latest_today_send_reply_media_to"] == "live_mcp"
    assert summary["route_current_latest_today_send_reply_media_to"] == rules.live_route_target
    assert summary["negative_results_claim"] == rules.negative_archive_claim
    assert summary["never_infer_absence_from_archive_only"] is True
