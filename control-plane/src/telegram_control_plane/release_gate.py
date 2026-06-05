from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from .paths import CONTROL_ROOT, MCP_REPO, POLICY_DIR, TG_CLI
from .util import load_json, status_from_findings

RELEASE_GATES_PATH = POLICY_DIR / "release-gates.json"


def _format_argv(argv: list[str]) -> list[str]:
    mapping = {
        "{control_root}": str(CONTROL_ROOT),
        "{mcp_repo}": str(MCP_REPO),
        "{tg_cli}": str(TG_CLI),
    }
    formatted: list[str] = []
    for part in argv:
        value = part
        for key, replacement in mapping.items():
            value = value.replace(key, replacement)
        formatted.append(value)
    return formatted


def load_release_gate_manifest(path: Path = RELEASE_GATES_PATH) -> dict[str, Any]:
    payload = load_json(path) or {}
    if not isinstance(payload.get("modes"), dict):
        raise ValueError(f"Invalid release gate manifest: {path}")
    if not isinstance(payload.get("gates"), dict):
        raise ValueError(f"Invalid release gate manifest: {path}")
    return payload


def _run_gate(gate_id: str, spec: dict[str, Any]) -> dict[str, Any]:
    raw_argv = spec.get("argv")
    if not isinstance(raw_argv, list) or not raw_argv:
        return {
            "id": gate_id,
            "status": "fail",
            "message": "Gate spec is missing argv.",
            "argv": [],
            "exit_code": None,
        }
    argv = _format_argv([str(item) for item in raw_argv])
    cwd_raw = spec.get("cwd")
    cwd = _format_argv([str(cwd_raw)])[0] if isinstance(cwd_raw, str) else None

    completed = subprocess.run(
        argv,
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    ok = completed.returncode == 0
    return {
        "id": gate_id,
        "status": "ok" if ok else "fail",
        "message": "passed" if ok else (completed.stderr.strip() or "non-zero exit"),
        "argv": argv,
        "exit_code": completed.returncode,
    }


def run_release_gates(*, mode: str = "local") -> dict[str, Any]:
    manifest = load_release_gate_manifest()
    modes = manifest["modes"]
    if mode not in modes:
        return {
            "status": "fail",
            "findings": [
                {
                    "id": "unknown_release_gate_mode",
                    "severity": "blocking",
                    "message": f"Unknown release gate mode {mode!r}.",
                    "known_modes": sorted(modes),
                }
            ],
            "mode": mode,
            "gates": [],
        }

    gate_ids = modes[mode]
    if not isinstance(gate_ids, list):
        gate_ids = []

    gates_catalog = manifest["gates"]
    results: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []

    for gate_id in gate_ids:
        if not isinstance(gate_id, str):
            continue
        spec = gates_catalog.get(gate_id)
        if not isinstance(spec, dict):
            findings.append(
                {
                    "id": "release_gate_undefined",
                    "severity": "blocking",
                    "message": f"Release gate {gate_id!r} is listed in mode {mode!r} but missing from gates catalog.",
                    "gate": gate_id,
                }
            )
            continue
        result = _run_gate(gate_id, spec)
        results.append(result)
        if result["status"] != "ok":
            findings.append(
                {
                    "id": "release_gate_failed",
                    "severity": "blocking",
                    "message": f"Release gate {gate_id!r} failed.",
                    "gate": gate_id,
                    "exit_code": result.get("exit_code"),
                }
            )

    return {
        "status": status_from_findings(findings),
        "findings": findings,
        "mode": mode,
        "manifest_path": str(RELEASE_GATES_PATH),
        "gates": results,
    }


def main(argv: list[str] | None = None) -> int:
    import sys

    args = argv if argv is not None else sys.argv[1:]
    mode = "ci" if "--ci" in args else "local"
    emit_json = "--json" in args

    report = run_release_gates(mode=mode)
    if emit_json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        for gate in report.get("gates", []):
            if not isinstance(gate, dict):
                continue
            label = gate.get("id", "?")
            if gate.get("status") == "ok":
                print(f"release-gate: {label} ok")
            else:
                print(f"release-gate: {label} failed", file=sys.stderr)
        if report.get("status") == "ok":
            print("release-gate: all checks passed")
        else:
            failed = sum(
                1 for gate in report.get("gates", []) if isinstance(gate, dict) and gate.get("status") != "ok"
            )
            print(f"release-gate: {failed} check(s) failed", file=sys.stderr)

    return 0 if report.get("status") == "ok" else 1