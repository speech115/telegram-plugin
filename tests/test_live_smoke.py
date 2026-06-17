from __future__ import annotations

import json
import subprocess

import pytest

from telegram_control_plane.audits import audit_mirror_preflight, build_registry
from telegram_control_plane.audits import audit_mcp_surface


pytestmark = pytest.mark.integration


def test_live_registry_has_expected_warn_shape() -> None:
    registry = build_registry()

    assert registry["status"] == "warn"
    assert registry["summary"]["blocking_findings"] == 0
    assert registry["summary"]["warning_findings"] >= 1
    assert registry["summary"]["components"]["docs"] == "ok"
    assert registry["summary"]["components"]["fast_read_adapter"] == "ok"
    assert registry["summary"]["components"]["mcp_surface"] == "ok"
    finding_ids = {item.get("id") for item in registry.get("findings", []) if isinstance(item, dict)}
    assert "telecrawl_known_gaps" in finding_ids


def test_live_mirror_preflight_blocks_recovery_checkout_promotion() -> None:
    report = audit_mirror_preflight()

    assert report["status"] == "fail"
    assert report["promotion_allowed"] is False
    gates = {gate["id"]: gate for gate in report["gates"]}
    assert gates["launchd_cold_mode"]["status"] == "ok"
    assert any(gate["status"] == "fail" for gate in gates.values())


def test_live_mcp_surface_exposes_full_agent_tools() -> None:
    report = audit_mcp_surface()

    assert report["status"] == "ok"
    for name in [
        "telegram_send",
        "send_dialog_message",
        "reply_in_dialog",
        "reply_message",
        "send_message",
        "reply_to_message",
        "delete_messages",
        "create_channel",
        "transcribe_voice",
        "read_today_dialog",
        "search_dialog_messages",
    ]:
        assert name in report["default_surface_tools"], f"missing full-surface tool: {name}"


def test_live_fast_read_adapter_reads_saved_messages() -> None:
    completed = subprocess.run(
        [
            "/Users/sereja/Projects/tools/telegram/bin/telegram-fast-read-today",
            "me",
            "--limit",
            "1",
            "--timeout",
            "20",
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=25,
    )

    payload = json.loads(completed.stdout)
    assert payload["ok"] is True
    assert payload["mode"] == "telegram_fast_read_today"
    assert payload["payload"]["data_source"] == "live_telegram"


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
