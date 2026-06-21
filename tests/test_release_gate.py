from __future__ import annotations

import json
from pathlib import Path

from telegram_control_plane.release_gate import (
    RELEASE_GATES_PATH,
    load_release_gate_manifest,
    run_release_gates,
)


def test_release_gate_manifest_defines_local_and_ci_modes() -> None:
    manifest = load_release_gate_manifest()
    assert "local" in manifest["modes"]
    assert "ci" in manifest["modes"]
    assert "managed-systems" in manifest["modes"]["local"]
    assert manifest["modes"]["ci"] == [
        "agent-docs-check",
        "docs-audit",
        "mcp-surface",
        "source-routing-audit",
        "pytest",
    ]


def test_release_gate_manifest_matches_shell_gate_ids() -> None:
    manifest = load_release_gate_manifest()
    local_ids = manifest["modes"]["local"]
    for gate_id in local_ids:
        assert gate_id in manifest["gates"], gate_id


def test_run_release_gates_ci_mode(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_run(argv, cwd=None, capture_output=True, text=True):
        calls.append(list(argv))
        return type("R", (), {"returncode": 0, "stderr": ""})()

    monkeypatch.setattr("telegram_control_plane.release_gate.subprocess.run", fake_run)

    report = run_release_gates(mode="ci")

    assert report["status"] == "ok"
    assert len(calls) == 5
    assert calls[0][-2:] == ["--check", "--json"] or "agent-docs-sync" in str(calls[0][0])


def test_release_gate_local_includes_golden_read_smoke() -> None:
    manifest = load_release_gate_manifest()
    assert "tg-read-smoke" in manifest["modes"]["local"]
    spec = manifest["gates"]["tg-read-smoke"]
    assert "telegram-golden-read-smoke" in spec["argv"][0]


def test_release_gate_local_includes_runtime_contract_smoke() -> None:
    manifest = load_release_gate_manifest()
    assert "runtime-contract-smoke" in manifest["modes"]["local"]
    assert "runtime-app-media-smoke" in manifest["modes"]["local"]
    assert "runtime-contract-smoke" in manifest["gates"]
    assert "runtime-app-media-smoke" in manifest["gates"]
    assert "contract-smoke" in manifest["gates"]["runtime-contract-smoke"]["argv"][0]
    assert manifest["gates"]["runtime-app-media-smoke"]["argv"][1:3] == [
        "--profile",
        "app-media",
    ]


def test_release_gate_policy_file_is_valid_json() -> None:
    payload = json.loads(RELEASE_GATES_PATH.read_text(encoding="utf-8"))
    assert payload["gates"]["mcp-surface"]["argv"][0].endswith("telegram-mcp-surface")
