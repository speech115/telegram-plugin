from __future__ import annotations

import json
from pathlib import Path

from telegram_control_plane.mcp_surface_probe import live_mcp_surface_probe


def test_live_mcp_surface_probe_uses_read_path(monkeypatch, tmp_path: Path) -> None:
    mcp_repo = tmp_path / "mcp"
    python_bin = mcp_repo / ".venv/bin/python"
    python_bin.parent.mkdir(parents=True)
    python_bin.write_text("#!/bin/sh\n", encoding="utf-8")
    (mcp_repo / "src").mkdir()
    captured: dict[str, object] = {}

    def fake_run(argv, text, capture_output, check, timeout):
        captured["script"] = argv[2]
        return type(
            "Completed",
            (),
            {
                "returncode": 0,
                "stdout": json.dumps(
                    {
                        "status": "ok",
                        "accounts": {
                            "main": {
                                "status": "ok",
                                "tool_count": 1,
                                "missing_required_tools": [],
                                "read_probe_ok": True,
                            }
                        },
                    }
                ),
                "stderr": "",
            },
        )()

    monkeypatch.setattr("telegram_control_plane.mcp_surface_probe.subprocess.run", fake_run)

    report = live_mcp_surface_probe({"telegram_read"}, accounts=["main"], mcp_repo=mcp_repo)

    assert report["status"] == "ok"
    assert report["accounts"]["main"]["read_probe_ok"] is True
    script = str(captured["script"])
    assert 'tool_name="telegram_read"' in script
    assert 'tool_name="get_me"' not in script
