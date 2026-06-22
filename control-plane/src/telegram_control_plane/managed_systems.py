from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from .util import load_json, status_from_findings

PACKAGE_ROOT = Path(__file__).resolve().parent
CONTROL_ROOT_ANCHOR = PACKAGE_ROOT.parent.parent
MANAGED_SYSTEMS_PATH = CONTROL_ROOT_ANCHOR / "policy/managed-systems.json"
HOME_PATH = str(Path.home())

ENV_BINDINGS = {
    "control_root": ("TELEGRAM_CONTROL_PLANE_ROOT", "TELEGRAM_CONTROL_ROOT"),
    "mcp_repo": ("TELEGRAM_MCP_REPO",),
    "plugin_package": ("TELEGRAM_PLUGIN_PACKAGE",),
    "plugin_source": ("TELEGRAM_PLUGIN_SOURCE",),
    "plugin_cache_root": ("TELEGRAM_PLUGIN_CACHE_ROOT",),
    "live_skill": ("TELEGRAM_LIVE_SKILL",),
    "local_mirror_skill": ("TELEGRAM_LOCAL_MIRROR_SKILL",),
    "mirror_root": ("TELEGRAM_MIRROR_ROOT",),
    "mirror_runtime_root": ("TELEGRAM_MIRROR_RUNTIME_ROOT",),
    "mirror_legacy_alias": ("TELEGRAM_MIRROR_LEGACY_ALIAS",),
    "telecrawl_archive": ("TELEGRAM_TELECRAWL_ARCHIVE",),
    "telecrawl_default_db": ("TELEGRAM_TELECRAWL_DEFAULT_DB",),
}

ENV_DERIVED = {
    "generated_dir": ("TELEGRAM_GENERATED_DIR",),
    "policy_dir": ("TELEGRAM_POLICY_DIR",),
    "fast_read_adapter": ("TELEGRAM_FAST_READ_ADAPTER",),
    "tg_cli": ("TELEGRAM_TG_CLI",),
    "observed_registry": ("TELEGRAM_OBSERVED_REGISTRY",),
    "launchagents_dir": ("TELEGRAM_LAUNCHAGENTS_DIR",),
    "mcp_telemetry_log": ("TELEGRAM_MCP_TELEMETRY_LOG",),
    "mcp_telemetry_dir": ("TELEGRAM_MCP_TELEMETRY_DIR",),
    "mcp_telemetry_stats": ("TELEGRAM_MCP_TELEMETRY_STATS",),
    "telemetry_alert_thresholds": ("TELEGRAM_TELEMETRY_ALERT_THRESHOLDS",),
}

ENV_SYSTEM_PATHS = {
    "telegram-mcp-env": ("TELEGRAM_MCP_ENV",),
}


def _env_path(names: tuple[str, ...]) -> Path | None:
    for name in names:
        raw = os.environ.get(name)
        if raw:
            return Path(os.path.expanduser(raw))
    return None


def _binding_env_path(binding_name: str, system_id: str) -> Path | None:
    if not system_id.startswith("telegram-"):
        return None
    return _env_path(ENV_BINDINGS.get(binding_name, ()))


def _system_env_path(system_id: str) -> Path | None:
    direct = _env_path(ENV_SYSTEM_PATHS.get(system_id, ()))
    if direct is not None:
        return direct
    if system_id == "telegram-mcp-env":
        mcp_repo = _env_path(ENV_BINDINGS["mcp_repo"])
        if mcp_repo is not None:
            return mcp_repo / ".env"
    return None


@dataclass(frozen=True)
class ManagedSystemRecord:
    id: str
    role: str
    path: Path
    expected_kind: str
    deletion_protection: str
    required_markers: tuple[str, ...]
    source_of_truth: bool
    safe_delete: str | None
    expected_resolved: Path | None


def _expand_path(raw: str, *, home: Path, resolved: dict[str, Path]) -> Path:
    value = raw.replace("$HOME", str(home)).replace("~/", f"{home}/")
    for name, path in resolved.items():
        token = f"${{{name}}}"
        if token in value:
            value = value.replace(token, str(path))
    return Path(os.path.expanduser(value))


def _systems_index(systems: list[dict[str, Any]]) -> dict[str, ManagedSystemRecord]:
    index: dict[str, ManagedSystemRecord] = {}
    for item in systems:
        if not isinstance(item, dict):
            continue
        system_id = str(item.get("id") or "")
        raw_path = str(item.get("path") or "")
        if not system_id or not raw_path:
            continue
        expected_resolved = item.get("expected_resolved")
        index[system_id] = ManagedSystemRecord(
            id=system_id,
            role=str(item.get("role") or ""),
            path=Path(raw_path),
            expected_kind=str(item.get("expected_kind") or "path"),
            deletion_protection=str(item.get("deletion_protection") or "blocking"),
            required_markers=tuple(
                str(marker) for marker in (item.get("required_markers") or []) if isinstance(marker, str)
            ),
            source_of_truth=bool(item.get("source_of_truth")),
            safe_delete=str(item.get("safe_delete")) if item.get("safe_delete") is not None else None,
            expected_resolved=Path(expected_resolved) if isinstance(expected_resolved, str) else None,
        )
    return index


@lru_cache(maxsize=4)
def load_managed_systems_policy(path: str = str(MANAGED_SYSTEMS_PATH)) -> dict[str, Any]:
    payload = load_json(Path(path)) or {}
    if not isinstance(payload.get("systems"), list):
        payload["systems"] = []
    return payload


def clear_policy_cache() -> None:
    load_managed_systems_policy.cache_clear()


def system_records(*, policy: dict[str, Any] | None = None) -> dict[str, ManagedSystemRecord]:
    payload = policy if policy is not None else load_managed_systems_policy()
    systems = payload.get("systems")
    if not isinstance(systems, list):
        return {}
    return _systems_index(systems)


def system_path(system_id: str, *, policy: dict[str, Any] | None = None) -> Path:
    return ControlPlaneTopology(policy=policy).system_path(system_id)


@dataclass(frozen=True)
class ControlPlaneTopology:
    policy: dict[str, Any] | None = None
    home: Path | None = None

    @property
    def payload(self) -> dict[str, Any]:
        return self.policy if self.policy is not None else load_managed_systems_policy()

    @property
    def records(self) -> dict[str, ManagedSystemRecord]:
        return system_records(policy=self.payload)

    def system_path(self, system_id: str) -> Path:
        record = self.records.get(system_id)
        if record is None:
            raise KeyError(f"Unknown managed system id: {system_id}")
        override = _system_env_path(system_id)
        if override is not None:
            return override
        topology = self.payload.get("topology") if isinstance(self.payload.get("topology"), dict) else {}
        bindings = topology.get("bindings") if isinstance(topology.get("bindings"), dict) else {}
        for binding_name, bound_system_id in bindings.items():
            if bound_system_id == system_id and isinstance(binding_name, str):
                override = _binding_env_path(binding_name, system_id)
                if override is not None:
                    return override
        return record.path

    def resolve(self) -> dict[str, Path]:
        home_path = self.home or Path.home()
        topology = self.payload.get("topology") if isinstance(self.payload.get("topology"), dict) else {}
        bindings = topology.get("bindings") if isinstance(topology.get("bindings"), dict) else {}
        derived = topology.get("derived") if isinstance(topology.get("derived"), dict) else {}

        resolved: dict[str, Path] = {}
        for name, system_id in bindings.items():
            if not isinstance(name, str) or not isinstance(system_id, str):
                continue
            record = self.records.get(system_id)
            if record is None:
                raise KeyError(f"Topology binding {name!r} references unknown system {system_id!r}")
            resolved[name] = _binding_env_path(name, system_id) or record.path

        for name, raw in derived.items():
            if not isinstance(name, str) or not isinstance(raw, str):
                continue
            resolved[name] = _env_path(ENV_DERIVED.get(name, ())) or _expand_path(raw, home=home_path, resolved=resolved)

        return resolved


def resolve_topology(*, policy: dict[str, Any] | None = None, home: Path | None = None) -> dict[str, Path]:
    return ControlPlaneTopology(policy=policy, home=home).resolve()


def substitute_policy_marker(
    marker: str,
    *,
    plugin_source_version: str | None,
    plugin_cache_version: str | None,
) -> str:
    version = plugin_source_version if plugin_source_version else (plugin_cache_version or "")
    return marker.replace("{plugin_source_version}", version)


def _expected_kind_matches(path: Path, expected_kind: str) -> bool:
    if expected_kind == "directory":
        return path.is_dir()
    if expected_kind == "file":
        return path.is_file()
    if expected_kind == "symlink":
        return path.is_symlink()
    if expected_kind == "path":
        return path.exists()
    return False


def _is_portable_repo_path(raw_path: str) -> bool:
    projects_root = os.environ.get("TELEGRAM_PROJECTS_ROOT")
    if not projects_root:
        return False
    try:
        Path(raw_path).resolve(strict=False).relative_to(Path(projects_root).resolve(strict=False))
    except ValueError:
        return False
    return True


def evaluate_managed_systems(
    *,
    policy: dict[str, Any] | None = None,
    plugin_source_version: str | None = None,
    plugin_cache_version: str | None = None,
) -> dict[str, Any]:
    payload = policy if policy is not None else load_managed_systems_policy()
    systems_policy = payload.get("systems") if isinstance(payload.get("systems"), list) else []
    records = system_records(policy=payload)
    portable_mode = os.environ.get("TELEGRAM_CI_PORTABLE") == "1"
    topology = payload.get("topology") if isinstance(payload.get("topology"), dict) else {}
    bindings = topology.get("bindings") if isinstance(topology.get("bindings"), dict) else {}
    system_bindings = {
        system_id: binding_name
        for binding_name, system_id in bindings.items()
        if isinstance(binding_name, str) and isinstance(system_id, str)
    }
    rows: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_paths: set[str] = set()

    for item in systems_policy:
        if not isinstance(item, dict):
            findings.append(
                {
                    "id": "managed_system_policy_item_invalid",
                    "severity": "blocking",
                    "message": "Managed systems policy contains a non-object entry.",
                }
            )
            continue
        system_id = str(item.get("id") or "")
        record = records.get(system_id)
        binding_name = system_bindings.get(system_id)
        env_override = _system_env_path(system_id) or (
            _binding_env_path(binding_name, system_id) if binding_name else None
        )
        raw_path = str(env_override or record.path) if record else str(item.get("path") or "")
        expected_kind = record.expected_kind if record else str(item.get("expected_kind") or "path")
        deletion_protection = record.deletion_protection if record else str(item.get("deletion_protection") or "blocking")
        if portable_mode and env_override is not None:
            expected_kind = "path"
        if (
            portable_mode
            and deletion_protection == "blocking"
            and (
                not bool(item.get("source_of_truth"))
                or not _is_portable_repo_path(raw_path)
            )
        ):
            deletion_protection = "warn"
        required_markers = record.required_markers if record else ()
        expected_resolved = str(record.expected_resolved) if record and record.expected_resolved else None
        if portable_mode and env_override is not None:
            expected_resolved = None
        path = Path(raw_path) if raw_path else Path()
        exists = bool(raw_path) and path.exists()
        kind_matches = exists and _expected_kind_matches(path, expected_kind)
        missing_markers = sorted(
            marker
            for marker in required_markers
            if not (path / substitute_policy_marker(
                marker,
                plugin_source_version=plugin_source_version,
                plugin_cache_version=plugin_cache_version,
            )).exists()
        )
        resolved = str(path.resolve(strict=False)) if raw_path else None
        row = {
            "id": system_id,
            "role": item.get("role"),
            "path": raw_path,
            "expected_kind": expected_kind,
            "exists": exists,
            "kind_matches": kind_matches,
            "missing_markers": missing_markers,
            "resolved": resolved,
            "source_of_truth": bool(item.get("source_of_truth")),
            "deletion_protection": deletion_protection,
            "safe_delete": item.get("safe_delete"),
        }
        if expected_resolved:
            row["expected_resolved"] = expected_resolved
        rows.append(row)

        if not system_id:
            findings.append(
                {
                    "id": "managed_system_missing_id",
                    "severity": "blocking",
                    "message": "Managed systems policy entry is missing id.",
                }
            )
        elif system_id in seen_ids:
            findings.append(
                {
                    "id": "managed_system_duplicate_id",
                    "severity": "blocking",
                    "system": system_id,
                    "message": "Managed systems policy contains a duplicate id.",
                }
            )
        seen_ids.add(system_id)

        if not raw_path:
            findings.append(
                {
                    "id": "managed_system_missing_path",
                    "severity": "blocking",
                    "system": system_id,
                    "message": "Managed systems policy entry is missing path.",
                }
            )
        elif raw_path in seen_paths and not (portable_mode and not bool(item.get("source_of_truth"))):
            findings.append(
                {
                    "id": "managed_system_duplicate_path",
                    "severity": "blocking",
                    "system": system_id,
                    "message": "Managed systems policy contains a duplicate path.",
                }
            )
        seen_paths.add(raw_path)

        if not exists:
            findings.append(
                {
                    "id": "managed_system_missing",
                    "severity": "blocking" if deletion_protection == "blocking" else "warn",
                    "system": system_id,
                    "role": item.get("role"),
                    "path": raw_path,
                    "message": "Registered Telegram managed system path is missing.",
                }
            )
        elif not kind_matches:
            findings.append(
                {
                    "id": "managed_system_kind_mismatch",
                    "severity": "blocking" if deletion_protection == "blocking" else "warn",
                    "system": system_id,
                    "path": raw_path,
                    "expected_kind": expected_kind,
                    "message": "Registered Telegram managed system path exists with the wrong kind.",
                }
            )
        elif missing_markers:
            findings.append(
                {
                    "id": "managed_system_marker_missing",
                    "severity": "blocking" if deletion_protection == "blocking" else "warn",
                    "system": system_id,
                    "path": raw_path,
                    "missing_markers": missing_markers,
                    "message": "Registered Telegram managed system exists but required marker files are missing.",
                }
            )
        elif expected_resolved and resolved != expected_resolved:
            findings.append(
                {
                    "id": "managed_system_resolved_target_mismatch",
                    "severity": "blocking" if deletion_protection == "blocking" else "warn",
                    "system": system_id,
                    "path": raw_path,
                    "resolved": resolved,
                    "expected_resolved": expected_resolved,
                    "message": "Registered Telegram managed system resolves to an unexpected target.",
                }
            )

    for binding_name, system_id in bindings.items():
        if not isinstance(binding_name, str) or not isinstance(system_id, str):
            findings.append(
                {
                    "id": "managed_topology_binding_invalid",
                    "severity": "blocking",
                    "message": "Topology binding must use string keys and system ids.",
                }
            )
            continue
        if system_id not in records:
            findings.append(
                {
                    "id": "managed_topology_unknown_system",
                    "severity": "blocking",
                    "binding": binding_name,
                    "system": system_id,
                    "message": "Topology binding references an unknown managed system id.",
                }
            )

    derived = topology.get("derived") if isinstance(topology.get("derived"), dict) else {}
    for binding_name, raw in derived.items():
        if not isinstance(binding_name, str) or not isinstance(raw, str):
            findings.append(
                {
                    "id": "managed_topology_derived_invalid",
                    "severity": "blocking",
                    "message": "Topology derived path must use string keys and path values.",
                }
            )

    control_plane = records.get("telegram-control-plane")
    control_plane_path = system_path("telegram-control-plane", policy=payload) if control_plane is not None else None
    if control_plane_path is not None and control_plane_path.resolve() != CONTROL_ROOT_ANCHOR.resolve():
        findings.append(
            {
                "id": "managed_topology_control_plane_anchor_drift",
                "severity": "blocking",
                "system": "telegram-control-plane",
                "policy_path": str(control_plane_path),
                "package_anchor": str(CONTROL_ROOT_ANCHOR),
                "message": "Managed-systems control-plane path does not match installed package anchor.",
            }
        )

    deletion_policy = payload.get("deletion_policy") if isinstance(payload.get("deletion_policy"), dict) else {}
    return {
        "status": status_from_findings(findings),
        "findings": findings,
        "systems": rows,
        "topology": {
            "bindings": bindings,
            "derived": derived,
            "resolved": {name: str(path) for name, path in resolve_topology(policy=payload).items()},
        },
        "deletion_policy": deletion_policy,
        "summary": {
            "registered": len(rows),
            "existing": sum(1 for row in rows if row.get("exists")),
            "blocking_protected": sum(1 for row in rows if row.get("deletion_protection") == "blocking"),
            "missing": sum(1 for row in rows if not row.get("exists")),
            "kind_mismatches": sum(1 for row in rows if row.get("exists") and not row.get("kind_matches")),
            "marker_mismatches": sum(1 for row in rows if row.get("missing_markers")),
        },
    }


def topology_summary() -> dict[str, str]:
    return {name: str(path) for name, path in resolve_topology().items()}


def shell_exports() -> str:
    topology = resolve_topology()
    lines = [f'export TELEGRAM_{name.upper()}="{path}"' for name, path in topology.items()]
    return "\n".join(lines)
