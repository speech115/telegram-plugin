from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from .paths import POLICY_DIR
from .util import load_json, status_from_findings

REGISTRY_SCHEMA_PATH = POLICY_DIR / "registry-schema.json"
REGISTRY_REDACTION_PATH = POLICY_DIR / "registry-redaction.json"


@dataclass(frozen=True)
class RegistryRedactionPolicy:
    drop_keys: frozenset[str]
    preserve_path_unless_substrings: tuple[str, ...]
    redact_string_substrings: tuple[str, ...]
    redact_string_prefixes: tuple[str, ...]
    scan_patterns: tuple[tuple[str, re.Pattern[str]], ...]


def _as_str_tuple(values: Any) -> tuple[str, ...]:
    if not isinstance(values, list):
        return ()
    return tuple(str(item) for item in values if isinstance(item, str))


def _as_scan_patterns(values: Any) -> tuple[tuple[str, re.Pattern[str]], ...]:
    if not isinstance(values, list):
        return ()
    patterns: list[tuple[str, re.Pattern[str]]] = []
    for item in values:
        if not isinstance(item, dict):
            continue
        pattern_id = str(item.get("id") or "")
        raw = item.get("pattern")
        if not pattern_id or not isinstance(raw, str):
            continue
        patterns.append((pattern_id, re.compile(raw)))
    return tuple(patterns)


@lru_cache(maxsize=4)
def load_registry_redaction_policy(path: str = str(REGISTRY_REDACTION_PATH)) -> RegistryRedactionPolicy:
    payload = load_json(Path(path)) or {}
    return RegistryRedactionPolicy(
        drop_keys=frozenset(_as_str_tuple(payload.get("drop_keys"))),
        preserve_path_unless_substrings=_as_str_tuple(payload.get("preserve_path_unless_substrings")),
        redact_string_substrings=_as_str_tuple(payload.get("redact_string_substrings")),
        redact_string_prefixes=_as_str_tuple(payload.get("redact_string_prefixes")),
        scan_patterns=_as_scan_patterns(payload.get("scan_patterns")),
    )


def clear_policy_cache() -> None:
    load_registry_redaction_policy.cache_clear()


def _path_is_private(path: str, policy: RegistryRedactionPolicy) -> bool:
    return any(marker in path for marker in policy.preserve_path_unless_substrings)


def _should_redact_string(value: str, policy: RegistryRedactionPolicy) -> bool:
    if any(marker in value for marker in policy.redact_string_substrings):
        return True
    return any(value.startswith(prefix) for prefix in policy.redact_string_prefixes)


def redact_for_persistence(
    value: Any,
    *,
    policy: RegistryRedactionPolicy | None = None,
) -> Any:
    rules = policy or load_registry_redaction_policy()
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if key in rules.drop_keys:
                continue
            if key == "path" and isinstance(item, str) and not _path_is_private(item, rules):
                result[key] = item
                continue
            result[key] = redact_for_persistence(item, policy=rules)
        return result
    if isinstance(value, list):
        return [redact_for_persistence(item, policy=rules) for item in value]
    if isinstance(value, str) and _should_redact_string(value, rules):
        return "<redacted>"
    return copy.deepcopy(value)


def load_component_field_allowlist(
    path: Path = REGISTRY_SCHEMA_PATH,
) -> dict[str, list[str]]:
    schema = load_json(path) or {}
    fields = schema.get("component_fields")
    if not isinstance(fields, dict):
        return {}
    return {
        name: [field for field in allowlist if isinstance(field, str)]
        for name, allowlist in fields.items()
        if isinstance(name, str) and isinstance(allowlist, list)
    }


def project_registry_component(
    name: str,
    report: dict[str, Any],
    *,
    fields_by_component: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    enriched = enrich_registry_component(name, report)
    fields_map = fields_by_component if fields_by_component is not None else load_component_field_allowlist()
    fields = fields_map.get(name)
    if not isinstance(fields, list) or not fields:
        fields = ["status", "findings"]
    return {field: enriched[field] for field in fields if field in enriched}


def enrich_registry_component(name: str, report: dict[str, Any]) -> dict[str, Any]:
    if name == "mcp_telemetry":
        summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
        tool_latency = summary.get("tool_latency") if isinstance(summary.get("tool_latency"), dict) else {}
        return {
            "status": report.get("status"),
            "findings": report.get("findings", []),
            "events_in_window": report.get("events_in_window"),
            "tool_errors": report.get("tool_errors"),
            "cache_hit_rate": report.get("cache_hit_rate"),
            "stats_file_present": report.get("stats_file_present"),
            "tools_observed": sorted(tool_latency.keys())[:8],
            "source_counts": report.get("source_counts"),
            "prometheus_targets": report.get("prometheus_targets"),
        }
    if name == "sessions":
        sessions = report.get("sessions") if isinstance(report.get("sessions"), list) else []
        policy = report.get("policy") if isinstance(report.get("policy"), dict) else {}
        registered_policy = policy.get("sessions") if isinstance(policy.get("sessions"), list) else []
        return {
            "status": report.get("status"),
            "findings": report.get("findings", []),
            "summary": {
                "discovered": len(sessions),
                "existing": sum(1 for item in sessions if isinstance(item, dict) and item.get("exists")),
                "registered": sum(1 for item in sessions if isinstance(item, dict) and item.get("registered")),
                "runtime_allowed": sum(
                    1 for item in sessions if isinstance(item, dict) and item.get("runtime_allowed")
                ),
                "schema_checked": sum(1 for item in sessions if isinstance(item, dict) and item.get("schema_checked")),
                "lease_checked": sum(1 for item in sessions if isinstance(item, dict) and item.get("lease_checked")),
            },
            "policy_summary": {
                "registered": len(registered_policy),
                "runtime_allowed": sum(
                    1 for item in registered_policy if isinstance(item, dict) and item.get("runtime_allowed")
                ),
                "recovery_runtime_allowed": sum(
                    1
                    for item in registered_policy
                    if isinstance(item, dict)
                    and str(item.get("owner", "")).startswith("telegram-mirror")
                    and item.get("runtime_allowed")
                ),
            },
        }
    if name == "telegram_mirror":
        runtime_state = report.get("runtime_state") if isinstance(report.get("runtime_state"), dict) else {}
        sessions = runtime_state.get("sessions") if isinstance(runtime_state.get("sessions"), list) else []
        recovery_sessions = (
            runtime_state.get("recovery_sessions") if isinstance(runtime_state.get("recovery_sessions"), list) else []
        )
        ledgers = runtime_state.get("ledgers") if isinstance(runtime_state.get("ledgers"), list) else []
        export_coverage = (
            runtime_state.get("export_coverage") if isinstance(runtime_state.get("export_coverage"), dict) else {}
        )
        return {
            **report,
            "runtime_state_summary": {
                "session_count": len(sessions),
                "recovery_session_count": len(recovery_sessions),
                "ledger_count": len(ledgers),
                "runtime_root_exists": bool(runtime_state.get("runtime_root_exists")),
                "runtime_exports_exists": bool(runtime_state.get("runtime_exports_exists")),
                "export_expected_count": export_coverage.get("expected_count"),
                "export_ready_count": export_coverage.get("ready_count"),
                "export_missing_count": export_coverage.get("missing_count"),
            },
        }
    if name == "telecrawl":
        accounts_payload = report.get("accounts") if isinstance(report.get("accounts"), dict) else {}
        accounts = accounts_payload.get("accounts") if isinstance(accounts_payload.get("accounts"), list) else []
        archive = report.get("default_archive_status") if isinstance(report.get("default_archive_status"), dict) else {}
        gap_policy = report.get("gap_policy")
        if not isinstance(gap_policy, dict):
            gap_policy = {}
        return {
            "status": report.get("status"),
            "findings": report.get("findings", []),
            "wrapper": report.get("wrapper"),
            "gap_policy": gap_policy,
            "freshness": report.get("freshness"),
            "account_summary": {
                "total": len(accounts),
                "active": sum(1 for item in accounts if isinstance(item, dict) and item.get("active")),
                "inactive": sum(1 for item in accounts if isinstance(item, dict) and not item.get("active")),
                "archive_ready": bool(archive.get("archive_ready")),
                "known_gap_count": (
                    archive.get("import_gaps", {}).get("errors")
                    if isinstance(archive.get("import_gaps"), dict)
                    else None
                ),
            },
        }
    if name == "mcp_profiles":
        profiles = report.get("profiles") if isinstance(report.get("profiles"), list) else []
        safe_profiles = []
        for profile in profiles:
            if not isinstance(profile, dict):
                continue
            safe_profiles.append(
                {
                    "label": profile.get("label"),
                    "port": profile.get("port"),
                    "loaded": profile.get("loaded"),
                    "write_policy": profile.get("write_policy"),
                }
            )
        return {**report, "profiles": safe_profiles}
    return dict(report)


def scan_persisted_registry(
    registry: dict[str, Any],
    *,
    policy: RegistryRedactionPolicy | None = None,
) -> list[dict[str, Any]]:
    rules = policy or load_registry_redaction_policy()
    encoded = json.dumps(registry, ensure_ascii=False)
    findings: list[dict[str, Any]] = []
    for pattern_id, pattern in rules.scan_patterns:
        if pattern.search(encoded):
            findings.append(
                {
                    "id": "registry_persisted_private_leak",
                    "severity": "blocking",
                    "pattern": pattern_id,
                    "message": "Persisted registry snapshot still contains private runtime detail.",
                }
            )
    contract = load_json(REGISTRY_SCHEMA_PATH) or {}
    persisted = contract.get("persisted_registry_contract")
    if isinstance(persisted, dict) and persisted.get("private_debug_raw_payloads_allowed") is True:
        findings.append(
            {
                "id": "registry_private_debug_allowed",
                "severity": "blocking",
                "message": "Registry schema must not allow private_debug_raw_payloads in persisted snapshots.",
            }
        )
    return findings


def audit_persisted_registry(registry: dict[str, Any]) -> dict[str, Any]:
    findings = scan_persisted_registry(registry)
    return {
        "status": status_from_findings(findings),
        "findings": findings,
    }