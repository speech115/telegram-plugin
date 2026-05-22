#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parent
EXPORTER = ROOT / "export_channel_subscribers.py"


def load_exporter():
    spec = importlib.util.spec_from_file_location("export_channel_subscribers", EXPORTER)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {EXPORTER}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeUser:
    id = 123
    first_name = "Ada"
    last_name = "Lovelace"
    username = "ada"
    bot = False
    access_hash = 999


def main() -> None:
    exporter = load_exporter()

    with tempfile.TemporaryDirectory() as tmp:
        seed = Path(tmp) / "seed.session"
        seed.write_text("stub", encoding="utf-8")
        env_file = Path(tmp) / ".env"
        env_file.write_text("TELEGRAM_API_ID=1\nTELEGRAM_API_HASH=hash\n", encoding="utf-8")
        with patch.dict(os.environ, {}, clear=True):
            with patch(
                "sys.argv",
                [
                    "export_channel_subscribers.py",
                    "@example",
                    "--env-file",
                    str(env_file),
                    "--seed-session",
                    str(seed),
                ],
            ):
                try:
                    exporter.parse_args()
                except SystemExit as exc:
                    assert "PII" in str(exc)
                else:
                    raise AssertionError("parse_args must require explicit PII acknowledgement")

    assert "access_hash" not in exporter.user_record(FakeUser())
    assert exporter.user_record(FakeUser(), include_access_hash=True)["access_hash"] == 999

    with tempfile.TemporaryDirectory() as tmp:
        out_dir = Path(tmp) / "out"
        runtime_dir = Path(tmp) / "runtime"
        runtime_dir.mkdir()

        records = {
            123: exporter.user_record(FakeUser()),
        }
        md_out, json_out = exporter.write_outputs(
            chat="@example",
            source="fixture",
            visible_count=2,
            records=records,
            out_dir=out_dir,
            diagnostics={"fixture": True},
        )
        payload = json.loads(json_out.read_text(encoding="utf-8"))
        json_raw = json_out.read_text(encoding="utf-8")
        md_raw = md_out.read_text(encoding="utf-8")
        assert payload["exported_count"] == 1
        assert payload["missing_vs_visible_count"] == 1
        assert payload["completeness"] == "api_visible_gap"
        assert "access_hash" not in payload["participants"][0]
        assert "access_hash" not in json_raw
        assert "checkpoint" not in json_raw
        assert "checkpoint" not in md_raw
        assert md_out.exists()

        checkpoint = exporter.checkpoint_path(runtime_dir, "@example")
        exporter.save_checkpoint(checkpoint, records, {"a"})
        loaded_records, completed = exporter.load_checkpoint(checkpoint)
        assert loaded_records[123]["username"] == "@ada"
        assert completed == {"a"}
        assert not list(out_dir.glob("*.session"))
        assert not list(out_dir.glob(".*checkpoint*.json"))

    print("exporter contract smoke passed")


if __name__ == "__main__":
    main()
