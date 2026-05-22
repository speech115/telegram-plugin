#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import tempfile
from pathlib import Path


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
        assert payload["exported_count"] == 1
        assert payload["missing_vs_visible_count"] == 1
        assert payload["completeness"] == "api_visible_gap"
        assert "access_hash" not in payload["participants"][0]
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
