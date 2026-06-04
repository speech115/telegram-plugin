from __future__ import annotations

import json
from pathlib import Path

from telegram_control_plane.golden_read_smoke import (
    GOLDEN_DIALOGS_PATH,
    extract_data_source,
    list_golden_dialogs,
    load_golden_dialog_manifest,
    read_argv,
    run_golden_read_smoke,
    validate_read_envelope,
)


def test_golden_dialog_manifest_loads_five_dialogs() -> None:
    manifest = load_golden_dialog_manifest()
    dialogs = list_golden_dialogs(manifest=manifest)
    assert len(dialogs) == 5
    ids = {item["id"] for item in dialogs}
    assert ids == {
        "saved-messages",
        "channel-konspekty",
        "dm-commercialclub",
        "dm-andrewbto",
        "dm-brexit-man",
    }


def test_read_argv_prefers_kit_tg_cli(tmp_path: Path, monkeypatch) -> None:
    tg = tmp_path / "tg"
    tg.write_text("#!/bin/sh\ntrue\n", encoding="utf-8")
    tg.chmod(0o755)
    monkeypatch.setattr("telegram_control_plane.golden_read_smoke.TG_CLI", tg)
    monkeypatch.setattr("telegram_control_plane.golden_read_smoke.shutil.which", lambda _: "/usr/bin/tg")
    assert read_argv(chat="me", limit=3) == [str(tg), "read", "today", "me", "--limit", "3", "--json"]


def test_validate_read_envelope_requires_live_telegram() -> None:
    ok, message, source = validate_read_envelope(
        {"ok": True, "data_source": "live_telegram", "payload": {"messages": []}}
    )
    assert ok is True
    assert source == "live_telegram"
    assert message == "passed"

    ok2, message2, source2 = validate_read_envelope(
        {
            "ok": True,
            "payload": {"data_source": "telecrawl_archive", "messages": []},
        }
    )
    assert ok2 is False
    assert source2 == "telecrawl_archive"
    assert "live_telegram" in message2


def test_extract_data_source_prefers_top_level() -> None:
    assert extract_data_source({"data_source": "live_telegram", "payload": {}}) == "live_telegram"
    assert extract_data_source({"payload": {"data_source": "live_telegram"}}) == "live_telegram"


def test_run_golden_read_smoke_skip_live(monkeypatch, tmp_path: Path) -> None:
    manifest = json.loads(GOLDEN_DIALOGS_PATH.read_text(encoding="utf-8"))
    path = tmp_path / "golden-dialogs.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")

    def fail_run(*_args, **_kwargs):
        raise AssertionError("subprocess should not run when skip_live is set")

    monkeypatch.setattr("telegram_control_plane.golden_read_smoke.subprocess.run", fail_run)

    report = run_golden_read_smoke(skip_live=True, manifest_path=path)
    assert report["status"] == "ok"
    assert report["skipped"] is True
    assert len(report["dialogs"]) == 5


def test_run_golden_read_smoke_happy_path(monkeypatch) -> None:
    envelope = json.dumps(
        {
            "ok": True,
            "data_source": "live_telegram",
            "elapsed_seconds": 0.4,
            "payload": {"data_source": "live_telegram", "messages": []},
        }
    )

    def fake_run(argv, **kwargs):
        return type("R", (), {"returncode": 0, "stdout": envelope, "stderr": ""})()

    monkeypatch.setattr("telegram_control_plane.golden_read_smoke.subprocess.run", fake_run)

    report = run_golden_read_smoke(dialog_ids=["saved-messages"], limit=1)
    assert report["status"] == "ok"
    assert report["dialogs"][0]["status"] == "ok"