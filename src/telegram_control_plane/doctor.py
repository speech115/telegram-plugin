from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .doctor_profiles import collect_profile_components, doctor_profile
from . import registry_redaction, runtime_inventory, source_routing
from .util import status_from_findings

ComponentReports = dict[str, dict[str, Any]]


class ControlPlaneDoctor:
    """Build and persist the read-only Telegram control-plane registry."""

    def __init__(
        self,
        component_collector: Callable[[], ComponentReports] | None = None,
        *,
        profile: str = "core",
    ) -> None:
        self._component_collector = component_collector
        self.profile = doctor_profile(profile)

    def collect_components(self) -> ComponentReports:
        if self._component_collector is not None:
            return self._component_collector()

        from . import audits

        cached: dict[str, dict[str, Any]] = {}

        def launchd() -> dict[str, Any]:
            if "launchd" not in cached:
                cached["launchd"] = audits.audit_launchd()
            return cached["launchd"]

        def sessions() -> dict[str, Any]:
            if "sessions" not in cached:
                cached["sessions"] = audits.audit_sessions()
            return cached["sessions"]

        def mirror() -> dict[str, Any]:
            if "telegram_mirror" not in cached:
                cached["telegram_mirror"] = audits.audit_mirror()
            return cached["telegram_mirror"]

        def runtime_inventory_report() -> dict[str, Any]:
            return runtime_inventory.audit_runtime_inventory(
                launchd_report=launchd(),
                sessions_report=sessions(),
                mirror_report=mirror(),
            )

        collectors = {
            "managed_systems": audits.audit_managed_systems,
            "docs": audits.audit_docs,
            "plugin_drift": audits.audit_plugin_drift,
            "mcp_telemetry": audits.audit_mcp_telemetry,
            "fast_read_adapter": audits.audit_fast_read_adapter,
            "golden_read_smoke": audits.audit_golden_read_smoke,
            "agent_docs_sync": audits.audit_agent_docs_sync,
            "release_gates": audits.audit_release_gates,
            "install_adapters": audits.audit_install_adapters,
            "mcp_surface": audits.audit_mcp_surface,
            "mcp_profiles": audits.audit_mcp_profiles,
            "source_routing": source_routing.audit_source_routing,
            "launchd": launchd,
            "sessions": sessions,
            "telegram_mirror": mirror,
            "mirror_fast_status": audits.audit_mirror_fast_status,
            "runtime_inventory": runtime_inventory_report,
            "telecrawl": audits.audit_telecrawl,
        }
        return collect_profile_components(collectors, profile_name=self.profile.name)

    def build_registry(self, raw_components: ComponentReports | None = None) -> dict[str, Any]:
        components_input = raw_components if raw_components is not None else self.collect_components()
        findings: list[dict[str, Any]] = []
        for component, report in components_input.items():
            for item in report.get("findings", []):
                enriched = dict(item)
                enriched.setdefault("component", component)
                findings.append(enriched)

        components = {
            name: registry_redaction.project_registry_component(name, report)
            for name, report in components_input.items()
        }
        registry = {
            "schema_version": 1,
            "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "profile": self.profile.name,
            "read_only_external_state": True,
            "status": status_from_findings(findings),
            "summary": {
                "components": {name: report.get("status") for name, report in components_input.items()},
                "blocking_findings": sum(1 for item in findings if item.get("severity") == "blocking"),
                "warning_findings": sum(1 for item in findings if item.get("severity") in {"warn", "warning"}),
            },
            "findings": findings,
            "components": components,
        }
        registry = registry_redaction.redact_for_persistence(registry)
        leak_report = registry_redaction.audit_persisted_registry(registry)
        for item in leak_report.get("findings", []):
            enriched = dict(item)
            enriched.setdefault("component", "registry_redaction")
            findings.append(enriched)
        if leak_report.get("findings"):
            registry["findings"] = findings
            registry["status"] = status_from_findings(findings)
            registry["summary"]["blocking_findings"] = sum(
                1 for entry in findings if entry.get("severity") == "blocking"
            )
        return registry

    def write_registry(self, path: Path, registry: dict[str, Any]) -> None:
        leak_report = registry_redaction.audit_persisted_registry(registry)
        if leak_report.get("status") == "fail":
            raise ValueError(
                "Refusing to write observed registry with private runtime leaks: "
                + ", ".join(item.get("pattern", item.get("id", "?")) for item in leak_report.get("findings", []))
            )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(registry, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_registry() -> dict[str, Any]:
    return ControlPlaneDoctor().build_registry()


def write_registry(path: Path, registry: dict[str, Any]) -> None:
    ControlPlaneDoctor().write_registry(path, registry)
