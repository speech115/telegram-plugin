from __future__ import annotations

import json
from pathlib import Path

import pytest

from telegram_control_plane import mirror_fast


def _write_fixture(tmp_path: Path) -> tuple[Path, Path]:
    config_root = tmp_path / "config"
    export_root = tmp_path / "exports"
    config_root.mkdir()
    (config_root / "telegram_channels.yaml").write_text(
        """
channels:
  - channel_id: "1001"
    name: PRIME CHAT
    username: prime_chat
    mirror_scope: prime-chat
    export_folder: people/prime/telegram/chats/PRIME CHAT
""".strip(),
        encoding="utf-8",
    )
    messages_path = export_root / "people/prime/telegram/chats/PRIME CHAT/messages_raw.jsonl"
    messages_path.parent.mkdir(parents=True)
    messages_path.write_text(
        "\n".join(
            [
                json.dumps({"id": 1, "date": "2026-06-10T10:00:00+00:00", "text_raw": "old"}),
                json.dumps({"id": 2, "date": "2026-06-12T10:00:00+00:00", "text_markdown": "fresh mirror note"}),
            ]
        ),
        encoding="utf-8",
    )
    return config_root, export_root


def test_read_messages_reads_existing_export_without_recovery_work(tmp_path: Path) -> None:
    config_root, export_root = _write_fixture(tmp_path)

    payload = mirror_fast.read_messages(
        query="prime-chat",
        date_from="2026-06-12",
        date_to="2026-06-12",
        limit=30,
        config_root=config_root,
        export_root=export_root,
    )

    assert payload["status"] == "ok"
    assert payload["message_count"] == 1
    assert payload["messages"][0]["text"] == "fresh mirror note"
    assert payload["messages"][0]["source"]["name"] == "PRIME CHAT"


def test_search_messages_can_filter_by_target(tmp_path: Path) -> None:
    config_root, export_root = _write_fixture(tmp_path)

    payload = mirror_fast.search_messages(
        text="mirror",
        target="prime",
        limit=10,
        config_root=config_root,
        export_root=export_root,
    )

    assert payload["status"] == "ok"
    assert payload["total_hits"] == 1
    assert payload["messages"][0]["id"] == 2


def test_read_messages_reports_missing_target(tmp_path: Path) -> None:
    config_root, export_root = _write_fixture(tmp_path)

    payload = mirror_fast.read_messages(
        query="missing",
        config_root=config_root,
        export_root=export_root,
    )

    assert payload["status"] == "warn"
    assert payload["error"] == "mirror_target_not_found"


def test_read_messages_rejects_zero_limit(tmp_path: Path) -> None:
    config_root, export_root = _write_fixture(tmp_path)

    with pytest.raises(ValueError, match="positive integer"):
        mirror_fast.read_messages(
            query="prime-chat",
            limit=0,
            config_root=config_root,
            export_root=export_root,
        )


def test_main_rejects_zero_limit(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        mirror_fast.main(["read", "prime-chat", "--limit", "0", "--json"])
    assert exc.value.code == 2
    assert "positive integer" in capsys.readouterr().err


def test_main_uses_provided_argv(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(
        mirror_fast,
        "build_status",
        lambda: {"status": "ok", "mode": "read_only_fast_mirror", "export_count": 0, "ledger_count": 0},
    )

    assert mirror_fast.main(["status", "--json"]) == 0

    assert '"mode": "read_only_fast_mirror"' in capsys.readouterr().out
