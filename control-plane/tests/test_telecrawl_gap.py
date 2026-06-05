from __future__ import annotations

import sqlite3
from pathlib import Path

from telegram_control_plane.telecrawl_gap import (
    import_gaps,
    known_gaps_findings,
    load_telecrawl_policy,
    non_retryable_error_types,
)


def test_telecrawl_policy_declares_expected_gap_warning() -> None:
    policy = load_telecrawl_policy()
    assert policy.get("known_gaps_are_blocking_for_archive_search") is False
    assert "telecrawl_known_gaps" in policy.get("expected_doctor_warning_ids", [])


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
    findings = known_gaps_findings(policy, {"has_known_gaps": True, "retryable_error_summary": [], "terminal_error_summary": []})
    assert findings[0]["id"] == "telecrawl_known_gaps"
    assert findings[0]["severity"] == "warn"
    assert findings[0]["expected_operational_warning"] is True


def test_non_retryable_error_types_defaults() -> None:
    policy = load_telecrawl_policy()
    types = non_retryable_error_types(policy)
    assert "ChannelPrivateError" in types