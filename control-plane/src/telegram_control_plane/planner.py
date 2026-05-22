from __future__ import annotations

from typing import Any

from .audits import build_registry
from .paths import CONTROL_ROOT, HOME, MCP_REPO, PLUGIN_CACHE, PLUGIN_SOURCE


def _finding_ids(registry: dict[str, Any]) -> set[str]:
    return {str(item.get("id")) for item in registry.get("findings", []) if isinstance(item, dict)}


def _component_status(registry: dict[str, Any], component: str) -> str | None:
    summary = registry.get("summary")
    if not isinstance(summary, dict):
        return None
    components = summary.get("components")
    if not isinstance(components, dict):
        return None
    value = components.get(component)
    return str(value) if value is not None else None


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
) -> dict[str, Any]:
    return {
        "id": step_id,
        "title": title,
        "status": status,
        "reason": reason,
        "touched_paths": touched_paths,
        "dry_run_commands": dry_run_commands,
        "apply_commands": apply_commands,
        "rollback": rollback,
        "verification_commands": verifies,
    }


def build_repair_plan(registry: dict[str, Any] | None = None) -> dict[str, Any]:
    registry = registry or build_registry()
    ids = _finding_ids(registry)
    steps: list[dict[str, Any]] = []

    managed_blocked = _component_status(registry, "managed_systems") == "fail"
    steps.append(
        _step(
            step_id="managed-systems-inventory",
            title="Verify Telegram managed systems inventory before any cleanup or repair",
            status="blocked_by_missing_or_wrong_managed_system" if managed_blocked else "already_clean",
            reason=(
                "A registered Telegram system is missing, has the wrong kind, or lacks required marker files."
                if managed_blocked
                else "Managed systems inventory is clean."
            ),
            touched_paths=[
                str(CONTROL_ROOT / "policy/managed-systems.json"),
                str(CONTROL_ROOT / "PROTECTION.md"),
            ],
            dry_run_commands=[
                [str(CONTROL_ROOT / "bin/telegram-managed-systems"), "--json"],
            ],
            apply_commands=[],
            rollback=[
                "Policy-only inventory changes can be reverted without touching actual Telegram systems.",
                "Do not delete or move any registered system from this step.",
            ],
            verifies=[
                [str(CONTROL_ROOT / "bin/telegram-managed-systems"), "--json"],
                [str(CONTROL_ROOT / "bin/telegram-doctor"), "--json"],
            ],
        )
    )

    plugin_blocked = _component_status(registry, "plugin_drift") == "fail"
    steps.append(
        _step(
            step_id="plugin-cache-parity",
            title="Normalize Telegram plugin source/cache/version parity",
            status="blocked_by_current_drift" if plugin_blocked else "already_clean",
            reason=(
                "Active plugin source/cache differ at the same version; repair must happen before trusting "
                "plugin behavior."
                if plugin_blocked
                else "Plugin drift gate is clean."
            ),
            touched_paths=[
                str(PLUGIN_SOURCE),
                str(PLUGIN_CACHE),
                str(HOME / ".codex/config.toml"),
                str(HOME / ".agents/plugins/marketplace.json"),
            ],
            dry_run_commands=[
                [str(MCP_REPO / "bin/check-plugin-drift"), "--json"],
                ["diff", "-ru", str(PLUGIN_SOURCE / "skills/telegram"), str(PLUGIN_CACHE / "skills/telegram")],
            ],
            apply_commands=[
                ["codex", "plugin", "marketplace", "remove", "local"],
                ["codex", "plugin", "marketplace", "add", str(PLUGIN_SOURCE.parent)],
            ],
            rollback=[
                "Leave older versioned cache directories intact.",
                "If installer output is wrong, disable the new cache by restoring the previous marketplace entry.",
            ],
            verifies=[
                [str(MCP_REPO / "bin/check-plugin-drift"), "--json"],
                ["${TELEGRAM_CONTROL_PLANE_ROOT:-./control-plane}/bin/telegram-plugin-drift", "--json"],
            ],
        )
    )

    mcp_surface_blocked = _component_status(registry, "mcp_surface") == "fail"
    steps.append(
        _step(
            step_id="mcp-surface-allowlist",
            title="Add hard allowlist/profile split for default Telegram MCP surface",
            status="blocked_by_current_surface" if mcp_surface_blocked else "already_clean",
            reason=(
                "Default Mode endpoint exposes low-level write/destructive tools and plugin metadata has no "
                "hard allowlist."
                if mcp_surface_blocked
                else "Default MCP surface gate is clean."
            ),
            touched_paths=[
                str(MCP_REPO / "src/telegram_mcp/tools/__init__.py"),
                str(PLUGIN_SOURCE / ".mcp.json"),
            ],
            dry_run_commands=[
                ["${TELEGRAM_CONTROL_PLANE_ROOT:-./control-plane}/bin/telegram-mcp-surface", "--json"],
            ],
            apply_commands=[
                [
                    "python3",
                    "-m",
                    "pytest",
                    "-q",
                    "tests/test_tool_surface.py",
                ]
            ],
            rollback=[
                "Revert the MCP profile/allowlist patch.",
                "Keep plugin .mcp.json on the prior endpoint until the server-side allowlist is verified.",
            ],
            verifies=[
                ["${TELEGRAM_CONTROL_PLANE_ROOT:-./control-plane}/bin/telegram-mcp-surface", "--json"],
                [str(MCP_REPO / "bin/contract-smoke"), "--json"],
            ],
        )
    )

    launchd_blocked = _component_status(registry, "launchd") == "fail"
    steps.append(
        _step(
            step_id="launchd-inventory-and-cold-mode",
            title="Reconcile Telegram launchd jobs with approved roots and cold mirror mode",
            status="blocked_by_launchd_drift" if launchd_blocked else "already_clean",
            reason=(
                "LaunchAgents reference legacy mirror paths, mirror jobs have autostart config, or loaded jobs "
                "are not represented by plist inventory."
                if launchd_blocked
                else "Launchd gate is clean."
            ),
            touched_paths=[
                "~/Library/LaunchAgents/com.example.telegram-*.plist",
                "~/Library/LaunchAgents/com.example.telecrawl*.plist",
                "${TELEGRAM_CONTROL_PLANE_ROOT:-./control-plane}/policy/allowed-roots.json",
            ],
            dry_run_commands=[
                ["${TELEGRAM_CONTROL_PLANE_ROOT:-./control-plane}/bin/telegram-launchd-audit", "--json"],
                ["launchctl", "list"],
            ],
            apply_commands=[],
            rollback=[
                "Before any plist write, copy the original plist to a timestamped local backup.",
                "Use launchctl bootout/bootstrap only from an explicit later migration step.",
            ],
            verifies=[
                ["${TELEGRAM_CONTROL_PLANE_ROOT:-./control-plane}/bin/telegram-launchd-audit", "--json"],
            ],
        )
    )

    sessions_blocked = _component_status(registry, "sessions") == "fail"
    steps.append(
        _step(
            step_id="session-registry",
            title="Create external Telegram session registry/broker inputs",
            status="blocked_by_missing_registry" if sessions_blocked else "already_clean",
            reason=(
                "Session files exist in recovery trees and no external owner/lease/schema registry exists."
                if sessions_blocked
                else "Session gate is clean."
            ),
            touched_paths=[
                "${TELEGRAM_CONTROL_PLANE_ROOT:-./control-plane}/policy/sessions.json",
            ],
            dry_run_commands=[
                ["${TELEGRAM_CONTROL_PLANE_ROOT:-./control-plane}/bin/telegram-session-audit", "--json"],
            ],
            apply_commands=[],
            rollback=[
                "Policy-only session registry can be removed without touching actual session files.",
                "Do not move or copy session files in this milestone.",
            ],
            verifies=[
                ["${TELEGRAM_CONTROL_PLANE_ROOT:-./control-plane}/bin/telegram-session-audit", "--json"],
            ],
        )
    )

    mirror_blocked = _component_status(registry, "telegram_mirror") == "fail"
    steps.append(
        _step(
            step_id="mirror-runtime-promotion-policy",
            title="Keep telegram-mirror recovery-scoped until runtime preflight exists",
            status="blocked_by_recovery_state" if mirror_blocked else "already_clean",
            reason=(
                "telegram-mirror has recovery/runtime ambiguity, sessions in-tree, or missing canonical runtime exports."
                if mirror_blocked
                else "Mirror gate is clean."
            ),
            touched_paths=[
                "${TELEGRAM_CONTROL_PLANE_ROOT:-./control-plane}/policy/source-routing.json",
                "${TELEGRAM_CONTROL_PLANE_ROOT:-./control-plane}-mirror",
            ],
            dry_run_commands=[
                ["${TELEGRAM_CONTROL_PLANE_ROOT:-./control-plane}/bin/telegram-mirror-audit", "--json"],
            ],
            apply_commands=[],
            rollback=[
                "Keep recovery classification until an explicit runtime preflight passes.",
            ],
            verifies=[
                ["${TELEGRAM_CONTROL_PLANE_ROOT:-./control-plane}/bin/telegram-mirror-audit", "--json"],
            ],
        )
    )

    telecrawl_blocked = _component_status(registry, "telecrawl") == "fail"
    steps.append(
        _step(
            step_id="telecrawl-archive-policy",
            title="Make telecrawl archive coverage explicit and non-live",
            status="blocked_by_known_gaps" if telecrawl_blocked else "already_clean",
            reason=(
                "Telecrawl default archive has known gaps or inactive accounts; it cannot answer current/latest claims."
                if telecrawl_blocked
                else "Telecrawl gate is clean."
            ),
            touched_paths=[
                "${TELEGRAM_CONTROL_PLANE_ROOT:-./control-plane}/policy/source-routing.json",
            ],
            dry_run_commands=[
                ["${TELEGRAM_CONTROL_PLANE_ROOT:-./control-plane}/bin/telegram-telecrawl-status", "--json"],
            ],
            apply_commands=[],
            rollback=[
                "Policy-only archive routing can be reverted without touching archive DBs.",
            ],
            verifies=[
                ["${TELEGRAM_CONTROL_PLANE_ROOT:-./control-plane}/bin/telegram-telecrawl-status", "--json"],
            ],
        )
    )

    recommended_order = [
        "managed-systems-inventory",
        "plugin-cache-parity",
        "mcp-surface-allowlist",
        "launchd-inventory-and-cold-mode",
        "session-registry",
        "mirror-runtime-promotion-policy",
        "telecrawl-archive-policy",
    ]
    return {
        "schema_version": 1,
        "status": "ready",
        "registry_status": registry.get("status"),
        "known_findings": sorted(ids),
        "recommended_order": recommended_order,
        "steps": steps,
        "safety": {
            "default_mode": "dry_run_only",
            "stateful_apply_requires_explicit_step": True,
            "do_not_do_first": [
                "move repos",
                "delete Telegram-related paths without managed-systems inventory",
                "rewrite LaunchAgents",
                "refresh plugin cache without dry-run evidence",
                "sync skill-index before plugin cache parity",
                "start mirror watchers/backfills/sync",
                "copy sessions",
            ],
        },
    }
