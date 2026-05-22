from __future__ import annotations

import json
import subprocess

import pytest

from telegram_control_plane.audits import audit_mirror_preflight, build_registry


pytestmark = pytest.mark.integration


def test_live_registry_keeps_default_mcp_surface_safe() -> None:
    registry = build_registry()

    assert registry["schema_version"] == 1
    assert registry["read_only_external_state"] is True
    assert registry["components"]["mcp_surface"]["status"] == "ok"
    assert not registry["components"]["mcp_surface"]["unexpected_write_or_destructive_tools"]


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
    for name in [
        "prepare_media_inspection_manifest",
        "download_media",
        "download_media_batch",
        "download_dialog_media",
        "transcribe_voice",
    ]:
        assert f"function {name}(" in output
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
        "tg:123456789",
        "telegram_user_id",
        "tdata_path",
        "db_path",
        "manifest_path",
        "~/.telegram-mcp/session.session",
        "~/.telegram-mcp-secondary/session.session",
    ]:
        assert marker not in encoded
