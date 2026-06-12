from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

ComponentCollector = Callable[[], dict[str, Any]]

CORE_COMPONENTS = (
    "fast_read_adapter",
    "mcp_surface",
    "source_routing",
    "launchd",
    "sessions",
    "mirror_fast_status",
)

MAINTENANCE_COMPONENTS = (
    "managed_systems",
    "docs",
    "plugin_drift",
    "mcp_telemetry",
    "fast_read_adapter",
    "golden_read_smoke",
    "agent_docs_sync",
    "release_gates",
    "install_adapters",
    "mcp_surface",
    "mcp_profiles",
    "source_routing",
    "launchd",
    "sessions",
    "telegram_mirror",
    "runtime_inventory",
    "telecrawl",
)

PROFILE_COMPONENTS = {
    "core": CORE_COMPONENTS,
    "maintenance": MAINTENANCE_COMPONENTS,
}


@dataclass(frozen=True)
class DoctorProfile:
    name: str
    components: tuple[str, ...]


def doctor_profile(name: str = "core") -> DoctorProfile:
    components = PROFILE_COMPONENTS.get(name)
    if components is None:
        known = ", ".join(sorted(PROFILE_COMPONENTS))
        raise ValueError(f"Unknown doctor profile {name!r}; expected one of: {known}")
    return DoctorProfile(name=name, components=components)


def collect_profile_components(
    collectors: dict[str, ComponentCollector],
    *,
    profile_name: str = "core",
) -> dict[str, dict[str, Any]]:
    profile = doctor_profile(profile_name)
    reports: dict[str, dict[str, Any]] = {}
    for component in profile.components:
        collector = collectors[component]
        reports[component] = collector()
    return reports
