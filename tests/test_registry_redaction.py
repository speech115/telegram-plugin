from __future__ import annotations

import json

from telegram_control_plane.registry_redaction import (
    audit_persisted_registry,
    load_registry_redaction_policy,
    project_registry_component,
    redact_for_persistence,
)


def test_redaction_policy_drops_private_keys() -> None:
    policy = load_registry_redaction_policy()
    assert "telegram_user_id" in policy.drop_keys
    assert "db_path" in policy.drop_keys


def test_redact_for_persistence_strips_session_and_account_details() -> None:
    payload = {
        "sessions": [{"path": "/Users/sereja/.telegram-mcp/session.session"}],
        "telecrawl": {
            "accounts": [{"telegram_user_id": "7091037467", "tdata_path": "/secret/tdata"}],
            "default_archive_status": {"db_path": "/Users/sereja/Projects/.artifacts/telecrawl/x.db"},
        },
        "label": "Telegram @CrwDdy",
        "account_key": "tg:7091037467",
    }
    redacted = redact_for_persistence(payload)
    encoded = json.dumps(redacted, ensure_ascii=False)
    assert "telegram_user_id" not in encoded
    assert "tdata_path" not in encoded
    assert "Telegram @" not in encoded
    assert "tg:7091037467" not in encoded
    assert ".session" not in encoded


def test_audit_persisted_registry_fails_on_private_leak() -> None:
    report = audit_persisted_registry({"note": "Telegram @example"})
    assert report["status"] == "fail"
    assert any(item["id"] == "registry_persisted_private_leak" for item in report["findings"])


def test_redact_for_persistence_normalizes_unix_home_paths() -> None:
    payload = {"path": "/Users/sereja/Projects/tools/telegram/bin/tg"}
    redacted = redact_for_persistence(payload)
    assert redacted["path"] == "<home>/Projects/tools/telegram/bin/tg"
    report = audit_persisted_registry(redacted)
    assert report["status"] == "ok"


def test_project_registry_component_uses_allowlist() -> None:
    projected = project_registry_component(
        "telecrawl",
        {
            "status": "warn",
            "findings": [],
            "wrapper": "/bin/telecrawl-archive",
            "gap_policy": {"is_live": False},
            "accounts": {"accounts": [{"telegram_user_id": "1"}]},
            "default_archive_status": {"archive_ready": True},
            "freshness": {"generated_at": "2026-06-04T00:00:00Z"},
        },
    )
    assert set(projected) == {"status", "findings", "wrapper", "gap_policy", "account_summary", "freshness"}
    assert "accounts" not in projected