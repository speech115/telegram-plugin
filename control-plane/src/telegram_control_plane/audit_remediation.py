from __future__ import annotations

import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

from .doctor import ControlPlaneDoctor
from .paths import CONTROL_ROOT, MCP_REPO, MIRROR_ROOT, PLUGIN_CACHE, PLUGIN_CACHE_ROOT, PLUGIN_SOURCE, POLICY_DIR
from .util import load_json

AUDIT_REMEDIATION_PATH = POLICY_DIR / "audit-remediation.json"
HOME = Path.home()

_TEMPLATE_VARS = {
    "CONTROL_ROOT": CONTROL_ROOT,
    "MCP_REPO": MCP_REPO,
    "MIRROR_ROOT": MIRROR_ROOT,
    "PLUGIN_CACHE": PLUGIN_CACHE,
    "PLUGIN_CACHE_ROOT": PLUGIN_CACHE_ROOT,
    "PLUGIN_SOURCE": PLUGIN_SOURCE,
    "HOME": HOME,
}


@lru_cache(maxsize=4)
def load_remediation_policy(path: str = str(AUDIT_REMEDIATION_PATH)) -> dict[str, Any]:
    return load_json(Path(path)) or {}


def build_registry() -> dict[str, Any]:
    return ControlPlaneDoctor(profile="maintenance").build_registry()


def clear_policy_cache() -> None:
    load_remediation_policy.cache_clear()


def _finding_ids(registry: dict[str, Any]) -> set[str]:
    return {str(item.get("id")) for item in registry.get("findings", []) if isinstance(item, dict)}


def _finding_by_id(registry: dict[str, Any], finding_id: str) -> dict[str, Any] | None:
    for item in registry.get("findings", []):
        if isinstance(item, dict) and item.get("id") == finding_id:
            return item
    return None


def _findings_for_component(registry: dict[str, Any], component: str) -> list[dict[str, Any]]:
    return [
        item
        for item in registry.get("findings", [])
        if isinstance(item, dict) and item.get("component") == component
    ]


def _component_status(registry: dict[str, Any], component: str) -> str | None:
    summary = registry.get("summary")
    if not isinstance(summary, dict):
        return None
    components = summary.get("components")
    if not isinstance(components, dict):
        return None
    value = components.get(component)
    return str(value) if value is not None else None


@dataclass(frozen=True)
class RemediationContext:
    registry: dict[str, Any]

    @property
    def finding_ids(self) -> set[str]:
        return _finding_ids(self.registry)

    def finding_by_id(self, finding_id: str) -> dict[str, Any] | None:
        return _finding_by_id(self.registry, finding_id)

    def findings_for_component(self, component: str) -> list[dict[str, Any]]:
        return _findings_for_component(self.registry, component)

    def component_status(self, component: str) -> str | None:
        return _component_status(self.registry, component)


class AuditRemediationPolicy:
    def __init__(self, payload: dict[str, Any] | None = None) -> None:
        self.payload = payload if payload is not None else load_remediation_policy()

    @property
    def safety(self) -> dict[str, Any]:
        safety = self.payload.get("safety")
        return safety if isinstance(safety, dict) else {}

    @property
    def auto_apply_ids(self) -> frozenset[str]:
        auto_apply_ids = self.payload.get("auto_apply_step_ids")
        if isinstance(auto_apply_ids, list):
            return frozenset(str(item) for item in auto_apply_ids if isinstance(item, str))
        return frozenset({"plugin-cache-materialize"})

    def steps_for_findings(self, context: RemediationContext) -> dict[str, list[str]]:
        mapping = self.payload.get("finding_to_steps")
        if not isinstance(mapping, dict):
            return {}
        result: dict[str, list[str]] = {}
        for finding_id, step_ids in mapping.items():
            if finding_id not in context.finding_ids or not isinstance(step_ids, list):
                continue
            result[str(finding_id)] = [str(step) for step in step_ids if isinstance(step, str)]
        return result

    def triggered_findings(self, context: RemediationContext, step_id: str) -> list[str]:
        finding_steps = self.steps_for_findings(context)
        return sorted(
            finding_id
            for finding_id, step_list in finding_steps.items()
            if step_id in step_list
        )

    def recommended_order(self, steps: list[dict[str, Any]]) -> list[str]:
        recommended_order = self.payload.get("recommended_order")
        if not isinstance(recommended_order, list):
            recommended_order = [step["id"] for step in steps]
        return [str(item) for item in recommended_order if isinstance(item, str)]

    def step_spec(self, step_id: str) -> dict[str, Any]:
        specs = self.payload.get("step_specs")
        if not isinstance(specs, dict):
            return {}
        spec = specs.get(step_id)
        return spec if isinstance(spec, dict) else {}

    def build_plan(self, registry: dict[str, Any]) -> dict[str, Any]:
        context = RemediationContext(registry)
        steps = _build_steps(context, self)
        return {
            "schema_version": 1,
            "status": "ready",
            "registry_status": registry.get("status"),
            "known_findings": sorted(context.finding_ids),
            "finding_remediation_map": self.steps_for_findings(context),
            "recommended_order": self.recommended_order(steps),
            "steps": steps,
            "safety": {
                **self.safety,
                "auto_apply_allowed_steps": sorted(self.auto_apply_ids),
            },
            "policy_path": str(AUDIT_REMEDIATION_PATH),
        }


def steps_for_findings(registry: dict[str, Any], *, policy: dict[str, Any] | None = None) -> dict[str, list[str]]:
    return AuditRemediationPolicy(policy).steps_for_findings(RemediationContext(registry))


def _mcp_surface_repair_reason(registry: dict[str, Any]) -> str:
    findings = _findings_for_component(registry, "mcp_surface")
    if not findings:
        return "Owner-local full MCP surface gate is clean."
    parts: list[str] = []
    for item in findings:
        finding_id = item.get("id")
        tools = item.get("tools")
        if isinstance(tools, list) and tools:
            parts.append(f"{finding_id}: {', '.join(str(tool) for tool in tools)}")
        else:
            parts.append(str(item.get("message") or finding_id))
    return "; ".join(parts)


def _step(
    *,
    step_id: str,
    title: str,
    status: str,
    reason: str,
    touched_paths: list[str],
    dry_run_commands: list[list[str]],
    apply_commands: list[list[str]],
    rollback: list[str],
    verifies: list[list[str]],
    auto_apply_allowed: bool = False,
    triggered_by_findings: list[str] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": step_id,
        "title": title,
        "status": status,
        "reason": reason,
        "touched_paths": touched_paths,
        "dry_run_commands": dry_run_commands,
        "apply_commands": apply_commands,
        "rollback": rollback,
        "verification_commands": verifies,
        "auto_apply_allowed": auto_apply_allowed,
    }
    if triggered_by_findings:
        payload["triggered_by_findings"] = triggered_by_findings
    return payload


def _expand_template(value: str) -> str:
    result = value
    for name, path in _TEMPLATE_VARS.items():
        result = result.replace("${" + name + "}", str(path))
    return result


def _expand_string_list(items: Any) -> list[str]:
    if not isinstance(items, list):
        return []
    return [_expand_template(item) for item in items if isinstance(item, str)]


def _expand_commands(items: Any) -> list[list[str]]:
    if not isinstance(items, list):
        return []
    commands: list[list[str]] = []
    for command in items:
        if not isinstance(command, list):
            continue
        expanded = [_expand_template(str(part)) for part in command]
        if expanded:
            commands.append(expanded)
    return commands


def _step_from_policy(
    policy: AuditRemediationPolicy,
    *,
    step_id: str,
    status: str,
    reason: str,
    apply_commands: list[list[str]] | None = None,
    auto_apply_allowed: bool | None = None,
    triggered_by_findings: list[str] | None = None,
) -> dict[str, Any]:
    spec = policy.step_spec(step_id)
    return _step(
        step_id=step_id,
        title=str(spec.get("title") or step_id),
        status=status,
        reason=reason,
        touched_paths=_expand_string_list(spec.get("touched_paths")),
        dry_run_commands=_expand_commands(spec.get("dry_run_commands")),
        apply_commands=_expand_commands(spec.get("apply_commands")) if apply_commands is None else apply_commands,
        rollback=_expand_string_list(spec.get("rollback")),
        verifies=_expand_commands(spec.get("verification_commands")),
        auto_apply_allowed=bool(spec.get("auto_apply_allowed")) if auto_apply_allowed is None else auto_apply_allowed,
        triggered_by_findings=triggered_by_findings,
    )


def _build_steps(context: RemediationContext, policy: AuditRemediationPolicy) -> list[dict[str, Any]]:
    registry = context.registry
    steps: list[dict[str, Any]] = []

    def triggers(step_id: str) -> list[str]:
        return policy.triggered_findings(context, step_id)

    managed_blocked = context.component_status("managed_systems") == "fail"
    steps.append(
        _step_from_policy(
            policy,
            step_id="managed-systems-inventory",
            status="blocked_by_missing_or_wrong_managed_system" if managed_blocked else "already_clean",
            reason=(
                "A registered Telegram system is missing, has the wrong kind, or lacks required marker files."
                if managed_blocked
                else "Managed systems inventory is clean."
            ),
            triggered_by_findings=triggers("managed-systems-inventory"),
        )
    )

    plugin_blocked = context.component_status("plugin_drift") == "fail"
    steps.append(
        _step_from_policy(
            policy,
            step_id="plugin-cache-parity",
            status="blocked_by_current_drift" if plugin_blocked else "already_clean",
            reason=(
                "Active plugin source/cache differ at the same version; repair must happen before trusting "
                "plugin behavior."
                if plugin_blocked
                else "Plugin drift gate is clean."
            ),
            triggered_by_findings=triggers("plugin-cache-parity"),
        )
    )

    materialize_warn = context.finding_by_id("plugin_cache_needs_materialization")
    materialize_cmd = (
        materialize_warn.get("materialize_command") if isinstance(materialize_warn, dict) else None
    )
    if not isinstance(materialize_cmd, list) or not materialize_cmd:
        materialize_cmd = [
            str(MCP_REPO / "bin/materialize-plugin-cache"),
            "--source-dir",
            str(PLUGIN_SOURCE),
            "--cache-root",
            str(PLUGIN_CACHE_ROOT),
            "--json",
        ]
    steps.append(
        _step_from_policy(
            policy,
            step_id="plugin-cache-materialize",
            status="ready_to_apply" if materialize_warn else "already_clean",
            reason=(
                "Plugin source is ahead of installed cache; copy the versioned cache tree locally."
                if materialize_warn
                else "Plugin cache matches source for the active version."
            ),
            apply_commands=[materialize_cmd] if materialize_warn else [],
            auto_apply_allowed=True,
            triggered_by_findings=triggers("plugin-cache-materialize") or ["plugin_cache_needs_materialization"],
        )
    )

    mcp_surface_blocked = context.component_status("mcp_surface") == "fail"
    steps.append(
        _step_from_policy(
            policy,
            step_id="mcp-surface-contract",
            status="needs_surface_contract_diagnosis" if mcp_surface_blocked else "already_clean",
            reason=_mcp_surface_repair_reason(registry),
            triggered_by_findings=triggers("mcp-surface-contract"),
        )
    )

    launchd_blocked = context.component_status("launchd") == "fail"
    steps.append(
        _step_from_policy(
            policy,
            step_id="launchd-inventory-and-cold-mode",
            status="blocked_by_launchd_drift" if launchd_blocked else "already_clean",
            reason=(
                "LaunchAgents reference legacy mirror paths, mirror jobs have autostart config, or loaded jobs "
                "are not represented by plist inventory."
                if launchd_blocked
                else "Launchd gate is clean."
            ),
            triggered_by_findings=triggers("launchd-inventory-and-cold-mode"),
        )
    )

    sessions_blocked = context.component_status("sessions") == "fail"
    steps.append(
        _step_from_policy(
            policy,
            step_id="session-registry",
            status="blocked_by_missing_registry" if sessions_blocked else "already_clean",
            reason=(
                "Session files exist in recovery trees and no external owner/lease/schema registry exists."
                if sessions_blocked
                else "Session gate is clean."
            ),
            triggered_by_findings=triggers("session-registry"),
        )
    )

    registry = context.registry
    mirror_status = context.component_status("telegram_mirror")
    mirror_blocked = mirror_status == "fail"
    mirror_exports_missing = bool(context.finding_ids & {"mirror_runtime_exports_missing", "mirror_runtime_exports_incomplete"})
    mirror_component = registry.get("components", {}).get("telegram_mirror")
    mirror_summary = (
        mirror_component.get("runtime_state_summary")
        if isinstance(mirror_component, dict) and isinstance(mirror_component.get("runtime_state_summary"), dict)
        else {}
    )
    mirror_export_counts = (
        f"{mirror_summary.get('export_ready_count')}/{mirror_summary.get('export_expected_count')} ready, "
        f"{mirror_summary.get('export_missing_count')} missing"
    )
    steps.append(
        _step_from_policy(
            policy,
            step_id="mirror-runtime-promotion-policy",
            status=(
                "blocked_by_recovery_state"
                if mirror_blocked
                else "needs_runtime_exports"
                if mirror_exports_missing
                else "already_clean"
            ),
            reason=(
                "telegram-mirror has recovery/runtime ambiguity, sessions in-tree, or missing canonical runtime exports."
                if mirror_blocked
                else f"Mirror export coverage is incomplete: {mirror_export_counts}."
                if mirror_exports_missing
                else "Mirror gate is clean."
            ),
            triggered_by_findings=triggers("mirror-runtime-promotion-policy"),
        )
    )

    telecrawl_blocked = context.component_status("telecrawl") == "fail"
    steps.append(
        _step_from_policy(
            policy,
            step_id="telecrawl-archive-policy",
            status="blocked_by_known_gaps" if telecrawl_blocked else "already_clean",
            reason=(
                "Telecrawl default archive has known gaps or inactive accounts; it cannot answer current/latest claims."
                if telecrawl_blocked
                else "Telecrawl gate is clean."
            ),
            triggered_by_findings=triggers("telecrawl-archive-policy"),
        )
    )
    return steps


def build_repair_plan(registry: dict[str, Any] | None = None) -> dict[str, Any]:
    return AuditRemediationPolicy().build_plan(registry or build_registry())


def _run_command(command: list[str], *, timeout: int = 120) -> dict[str, Any]:
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )
    return {
        "command": command,
        "exit_code": completed.returncode,
        "stdout": (completed.stdout or "").strip(),
        "stderr": (completed.stderr or "").strip(),
    }


def apply_repair_plan(
    registry: dict[str, Any] | None = None,
    *,
    step_ids: Iterable[str] | None = None,
    verify: bool = True,
) -> dict[str, Any]:
    policy = AuditRemediationPolicy()
    default_allowed = policy.auto_apply_ids
    plan = build_repair_plan(registry)
    allowed = frozenset(step_ids) if step_ids is not None else default_allowed
    by_id = {step["id"]: step for step in plan["steps"]}
    applied: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    failures: list[dict[str, Any]] = []

    for step_id in plan["recommended_order"]:
        if step_id not in allowed:
            continue
        step = by_id.get(step_id)
        if step is None:
            continue
        if not step.get("auto_apply_allowed"):
            skipped.append({"id": step_id, "reason": "not_auto_apply_allowed"})
            continue
        if step.get("status") != "ready_to_apply":
            skipped.append({"id": step_id, "reason": f"status={step.get('status')}"})
            continue
        commands = step.get("apply_commands")
        if not isinstance(commands, list) or not commands:
            skipped.append({"id": step_id, "reason": "no_apply_commands"})
            continue

        step_runs: list[dict[str, Any]] = []
        step_failed = False
        for command in commands:
            if not isinstance(command, list) or not command:
                continue
            run = _run_command([str(part) for part in command])
            step_runs.append(run)
            if run["exit_code"] != 0:
                step_failed = True
                failures.append({"step_id": step_id, **run})
                break

        applied.append({"id": step_id, "runs": step_runs, "status": "fail" if step_failed else "ok"})
        if step_failed:
            break

        if verify:
            verify_runs: list[dict[str, Any]] = []
            for command in step.get("verification_commands", []):
                if not isinstance(command, list) or not command:
                    continue
                run = _run_command([str(part) for part in command], timeout=180)
                verify_runs.append(run)
                if run["exit_code"] != 0:
                    failures.append({"step_id": step_id, "phase": "verify", **run})
                    step_failed = True
                    break
            applied[-1]["verify_runs"] = verify_runs
            if step_failed:
                break

    status = "fail" if failures else ("ok" if applied else "noop")
    return {
        "schema_version": 1,
        "status": status,
        "allowed_steps": sorted(allowed),
        "applied": applied,
        "skipped": skipped,
        "failures": failures,
    }
