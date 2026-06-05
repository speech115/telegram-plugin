from __future__ import annotations

from telegram_control_plane.audit_remediation import (
    AuditRemediationPolicy,
    RemediationContext,
    build_repair_plan,
    load_remediation_policy,
    steps_for_findings,
)


def test_remediation_policy_maps_known_gaps() -> None:
    policy = load_remediation_policy()
    mapping = policy.get("finding_to_steps")
    assert mapping["telecrawl_known_gaps"] == ["telecrawl-archive-policy"]


def test_steps_for_findings_links_materialize() -> None:
    registry = {
        "findings": [
            {"id": "plugin_cache_needs_materialization", "component": "plugin_drift", "severity": "warn"},
        ]
    }
    linked = steps_for_findings(registry)
    assert linked["plugin_cache_needs_materialization"] == ["plugin-cache-materialize"]


def test_audit_remediation_policy_owns_order_safety_and_triggers() -> None:
    registry = {
        "findings": [
            {"id": "telecrawl_known_gaps", "component": "telecrawl", "severity": "warn"},
        ]
    }
    context = RemediationContext(registry)
    policy = AuditRemediationPolicy()

    assert policy.auto_apply_ids == frozenset({"plugin-cache-materialize"})
    assert policy.safety["default_mode"] == "dry_run_only"
    assert policy.triggered_findings(context, "telecrawl-archive-policy") == ["telecrawl_known_gaps"]
    assert policy.recommended_order([{"id": "fallback"}])[0] == "managed-systems-inventory"


def test_build_repair_plan_includes_finding_remediation_map(monkeypatch) -> None:
    from telegram_control_plane import audits

    monkeypatch.setattr(
        audits,
        "_collect_components",
        lambda: {
            "managed_systems": {"status": "ok", "findings": []},
            "plugin_drift": {"status": "warn", "findings": []},
            "docs": {"status": "ok", "findings": []},
            "mcp_surface": {"status": "ok", "findings": []},
            "mcp_profiles": {"status": "ok", "findings": []},
            "source_routing": {"status": "ok", "findings": []},
            "launchd": {"status": "ok", "findings": []},
            "sessions": {"status": "ok", "findings": []},
            "telegram_mirror": {"status": "ok", "findings": []},
            "runtime_inventory": {"status": "ok", "findings": [], "summary": {}},
            "telecrawl": {"status": "warn", "findings": [{"id": "telecrawl_known_gaps", "severity": "warn"}]},
            "mcp_telemetry": {"status": "ok", "findings": []},
            "fast_read_adapter": {"status": "ok", "findings": []},
            "agent_docs_sync": {"status": "ok", "findings": []},
            "release_gates": {"status": "ok", "findings": []},
            "install_adapters": {"status": "ok", "findings": []},
        },
    )
    plan = build_repair_plan()
    assert "telecrawl_known_gaps" in plan["finding_remediation_map"]
    telecrawl_step = next(step for step in plan["steps"] if step["id"] == "telecrawl-archive-policy")
    assert "telecrawl_known_gaps" in telecrawl_step.get("triggered_by_findings", [])
