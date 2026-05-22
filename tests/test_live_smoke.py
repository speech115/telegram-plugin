from __future__ import annotations

import json
import subprocess

import pytest

from telegram_control_plane.audits import audit_mirror_preflight, build_registry


pytestmark = pytest.mark.integration


def test_live_registry_has_expected_warn_shape() -> None:
    registry = build_registry()

    assert registry["status"] == "warn"
    assert registry["summary"]["blocking_findings"] == 0
    assert registry["summary"]["warning_findings"] == 5


def test_live_mirror_preflight_blocks_recovery_checkout_promotion() -> None:
    report = audit_mirror_preflight()

    assert report["status"] == "fail"
    assert report["promotion_allowed"] is False
    gates = {gate["id"]: gate for gate in report["gates"]}
    assert gates["launchd_cold_mode"]["status"] == "ok"
    assert gates["session_externalization"]["status"] == "fail"


def test_live_mcporter_default_surface_has_no_write_tools() -> None:
    completed = subprocess.run(
        ["mcporter", "list", "telegram"],
        check=True,
        capture_output=True,
        text=True,
        timeout=20,
    )

    output = completed.stdout
    assert "15 tools" in output
    for name in [
        "send_dialog_message",
        "reply_in_dialog",
        "reply_message",
        "send_message",
        "reply_to_message",
        "delete_messages",
        "create_channel",
    ]:
        assert f"function {name}(" not in output


def test_live_persisted_registry_has_no_private_markers() -> None:
    registry = build_registry()
    encoded = json.dumps(registry, ensure_ascii=False)

    for marker in [
        "Telegram @",
        "tg:7091037467",
        "telegram_user_id",
        "tdata_path",
        "db_path",
        "manifest_path",
        "/Users/sereja/.telegram-mcp/session.session",
        "/Users/sereja/.telegram-mcp-pl/session.session",
    ]:
        assert marker not in encoded
