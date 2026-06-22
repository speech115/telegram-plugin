from __future__ import annotations

import json
import subprocess

from telegram_control_plane.runtime_compat import audit_runtime_compat, runtime_compat_probe
from telegram_control_plane.runtime_compat import live_runtime_compat_probe


def test_runtime_compat_probe_reports_patch_state() -> None:
    payload = runtime_compat_probe()

    assert payload["ok"] is True
    assert payload["channel_from_reader_patched"] is True
    assert payload["channel_from_reader_module"] == "telegram_mcp.telethon_compat"
    assert payload["constructor_aliases_ok"] is True


def test_audit_runtime_compat_prefers_live_doctor_contract(monkeypatch) -> None:
    monkeypatch.setattr(
        "telegram_control_plane.runtime_compat.live_runtime_compat_probe",
        lambda: {
            "ok": True,
            "probe_source": "live_doctor",
            "channel_from_reader_patched": True,
            "channel_from_reader_module": "telegram_mcp.telethon_compat",
            "constructor_aliases_ok": True,
        },
    )

    report = audit_runtime_compat()

    assert report["status"] == "ok"
    assert report["probe"]["probe_source"] == "live_doctor"
    assert report["fallback_probe"] is None


def test_live_runtime_compat_probe_reads_tg_doctor_envelope(monkeypatch) -> None:
    monkeypatch.setattr(
        "telegram_control_plane.runtime_compat.run_json",
        lambda *args, **kwargs: {
            "ok": True,
            "payload": {
                "runtime_compat": {
                    "ok": True,
                    "channel_from_reader_patched": True,
                    "channel_from_reader_module": "telegram_mcp.telethon_compat",
                    "constructor_aliases_ok": True,
                }
            },
            "exit_code": 0,
        },
    )

    payload = live_runtime_compat_probe()

    assert payload["ok"] is True
    assert payload["probe_source"] == "live_doctor"


def test_audit_runtime_compat_blocks_when_live_doctor_lacks_contract(monkeypatch) -> None:
    monkeypatch.setattr(
        "telegram_control_plane.runtime_compat.live_runtime_compat_probe",
        lambda: {
            "ok": False,
            "probe_source": "live_doctor",
            "missing_runtime_compat": True,
            "doctor_exit_code": 0,
        },
    )

    report = audit_runtime_compat()

    assert report["status"] == "fail"
    assert report["findings"][0]["details"]["missing_runtime_compat"] is True
    assert report["fallback_probe"] is None


def test_audit_runtime_compat_falls_back_when_live_doctor_is_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(
        "telegram_control_plane.runtime_compat.live_runtime_compat_probe",
        lambda: {
            "ok": False,
            "probe_source": "live_doctor",
            "doctor_unavailable": True,
            "doctor_exit_code": 2,
        },
    )

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(
            args=args[0],
            returncode=0,
            stdout=json.dumps(
                {
                    "ok": False,
                    "channel_from_reader_patched": False,
                    "channel_from_reader_module": "telethon.tl.types",
                    "constructor_aliases_ok": True,
                }
            ),
            stderr="",
        )

    monkeypatch.setattr("telegram_control_plane.runtime_compat.subprocess.run", fake_run)

    report = audit_runtime_compat()

    assert report["status"] == "fail"
    assert report["findings"][0]["id"] == "runtime_compat_not_applied"
    assert report["probe"]["probe_source"] == "subprocess_import"
    assert report["fallback_probe"] == report["probe"]
