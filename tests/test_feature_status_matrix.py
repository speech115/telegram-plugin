from __future__ import annotations

import csv
import json
from pathlib import Path

from telegram_control_plane.command_registry import COMMAND_REGISTRY
from telegram_control_plane.feature_status import feature_rows as projected_feature_rows


ROOT = Path(__file__).resolve().parents[1]
FEATURE_STATUS_PATH = ROOT / "docs/agents/feature-status.csv"
SURFACE_CONTRACT_PATH = ROOT / "policy/surface-contract.json"
RELEASE_GATES_PATH = ROOT / "policy/release-gates.json"
OPTIMIZATION_BASELINE_PATH = ROOT / "docs/agents/optimization-baseline.json"

REQUIRED_COLUMNS = {
    "feature_id",
    "surface",
    "feature_name",
    "user_story",
    "expected_behavior",
    "coverage_target",
    "coverage_source",
    "owning_files",
    "existing_checks",
    "verification_command",
    "command_name",
    "command_level",
    "command_safety",
    "command_class",
    "verification_mode",
    "expected_failure_class",
    "live_dependency",
    "mutates_state",
    "release_gate_id",
    "baseline_latency_ms",
    "post_fix_latency_ms",
    "code_status",
    "host_status",
    "optimization_opportunity",
    "optimization_verdict",
    "optimization_evidence",
    "proof_type",
    "status",
    "last_result",
    "errors",
    "next_action",
}


def feature_rows() -> list[dict[str, str]]:
    return projected_feature_rows(path=FEATURE_STATUS_PATH)


def raw_feature_rows() -> list[dict[str, str]]:
    with FEATURE_STATUS_PATH.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_feature_status_has_hardened_schema() -> None:
    rows = feature_rows()

    assert rows
    assert REQUIRED_COLUMNS <= set(rows[0]), sorted(REQUIRED_COLUMNS - set(rows[0]))
    for row in rows:
        assert row["feature_id"], row
        assert row["coverage_target"], row["feature_id"]
        assert row["verification_command"], row["feature_id"]
        assert row["command_class"], row["feature_id"]
        assert row["verification_mode"], row["feature_id"]
        assert row["code_status"], row["feature_id"]
        assert row["host_status"], row["feature_id"]
        assert row["optimization_verdict"], row["feature_id"]
        assert row["optimization_evidence"], row["feature_id"]
        assert row["proof_type"], row["feature_id"]


def test_every_registered_command_has_feature_status_coverage() -> None:
    rows = feature_rows()
    covered = {row["command_name"] for row in rows}
    missing = [spec.name for spec in COMMAND_REGISTRY if spec.name not in covered]

    assert missing == []


def test_required_mcp_surface_tools_have_feature_status_coverage() -> None:
    policy = json.loads(SURFACE_CONTRACT_PATH.read_text(encoding="utf-8"))
    required_tools = policy["owner_local_full_mcp"]["required_tools"]
    targets = {row["coverage_target"] for row in feature_rows()}

    missing = [tool for tool in required_tools if f"mcp_tool:{tool}" not in targets]

    assert missing == []


def test_mcp_surface_rows_are_generated_projection_not_manual_csv() -> None:
    raw_ids = {row["feature_id"] for row in raw_feature_rows()}
    projected_ids = {row["feature_id"] for row in feature_rows()}

    assert not any(feature_id.startswith("MCP-") for feature_id in raw_ids)
    assert "MCP-001" in projected_ids
    assert "MCP-019" in projected_ids


def test_doc_contract_rows_do_not_claim_behavior_proof() -> None:
    for row in feature_rows():
        if row["proof_type"] != "doc-contract-only":
            continue
        assert row["command_class"] == "doc-contract", row["feature_id"]
        assert row["code_status"] == "needs_behavior_probe", row["feature_id"]
        assert "doc_contract" in row["status"], row["feature_id"]
        assert "behavior" in row["optimization_opportunity"], row["feature_id"]


def test_no_skill_row_is_left_with_doc_only_proof() -> None:
    doc_only_skill_rows = [
        row["feature_id"]
        for row in feature_rows()
        if row["surface"] in {"skill", "plugin"} and row["proof_type"] == "doc-contract-only"
    ]

    assert doc_only_skill_rows == []


def test_mutating_and_guarded_commands_use_safe_verification_modes() -> None:
    rows = feature_rows()
    by_name = {spec.name: spec for spec in COMMAND_REGISTRY}

    for row in rows:
        spec = by_name.get(row["command_name"])
        if spec is None or spec.safety not in {"mutating", "guarded"}:
            continue
        assert row["mutates_state"] == "true", row["feature_id"]
        assert row["verification_mode"] == "safe-local", row["feature_id"]
        assert row["command_class"] in {"check-mode", "dry-run", "guarded"}, row["feature_id"]
        if spec.safety == "guarded":
            assert "pytest" in row["verification_command"], row["feature_id"]


def test_release_gate_metadata_supports_optimization_ordering() -> None:
    manifest = json.loads(RELEASE_GATES_PATH.read_text(encoding="utf-8"))
    required = {
        "cost_tier",
        "live_required",
        "mutates_state",
        "operational_vs_code",
        "can_run_offline",
    }
    for gate_id, spec in manifest["gates"].items():
        assert required <= set(spec), gate_id
        assert spec["cost_tier"] in {"cheap", "medium", "expensive", "live"}, gate_id
        assert isinstance(spec["live_required"], bool), gate_id
        assert isinstance(spec["mutates_state"], bool), gate_id
        assert spec["operational_vs_code"] in {"code", "operational", "mixed", "live"}, gate_id
        assert isinstance(spec["can_run_offline"], bool), gate_id


def test_every_feature_has_actionable_optimization_verdict() -> None:
    allowed = {"improved", "acceptable", "blocked", "not_worth_changing"}
    for row in feature_rows():
        assert row["optimization_verdict"] in allowed, row["feature_id"]
        assert len(row["optimization_evidence"]) >= 20, row["feature_id"]
        if row["host_status"] == "fail":
            assert row["optimization_verdict"] == "blocked", row["feature_id"]
            assert row["expected_failure_class"] != "none", row["feature_id"]
        if row["optimization_verdict"] == "blocked":
            assert row["host_status"] == "fail", row["feature_id"]


def test_optimization_baseline_matches_feature_status_matrix() -> None:
    rows = feature_rows()
    baseline = json.loads(OPTIMIZATION_BASELINE_PATH.read_text(encoding="utf-8"))

    assert baseline["schema_version"] == 1
    assert baseline["feature_status"]["path"] == "docs/agents/feature-status.csv"
    assert baseline["feature_status"]["rows"] == len(rows)

    csv_host_blockers = [
        {
            "feature_id": row["feature_id"],
            "feature_name": row["feature_name"],
            "expected_failure_class": row["expected_failure_class"],
            "errors": row["errors"],
            "next_action": row["next_action"],
        }
        for row in rows
        if row["host_status"] == "fail"
    ]
    assert baseline["feature_status"]["host_blockers"] == csv_host_blockers
    verdict_counts: dict[str, int] = {}
    for row in rows:
        verdict_counts[row["optimization_verdict"]] = (
            verdict_counts.get(row["optimization_verdict"], 0) + 1
        )
    assert baseline["feature_status"]["optimization_verdicts"] == verdict_counts

    gate_ids = {item["id"] for item in baseline["safe_gate_results"]}
    assert {
        "managed-systems",
        "source-routing-audit",
        "telemetry-status",
        "insights",
        "plugin-drift",
        "release-gates",
        "fast-read-today",
    } <= gate_ids

    by_gate = {item["id"]: item for item in baseline["safe_gate_results"]}
    by_feature = {row["feature_id"]: row for row in rows}
    if by_gate["fast-read-today"]["exit_code"] != 0:
        assert by_feature["CLI-006"]["host_status"] == "fail"
        assert by_feature["CLI-006"]["expected_failure_class"] == "live_runtime_flaky"
