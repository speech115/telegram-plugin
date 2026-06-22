from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Callable

from .catalog import CORE_COMPONENTS, MAINTENANCE_COMPONENTS, PROFILE_COMPONENTS, ControlPlaneCatalog

ComponentCollector = Callable[[], dict[str, Any]]


@dataclass(frozen=True)
class DoctorProfile:
    name: str
    components: tuple[str, ...]


def doctor_profile(name: str = "core") -> DoctorProfile:
    catalog = ControlPlaneCatalog.default()
    try:
        components = catalog.profile_components(name)
    except KeyError as exc:
        known = ", ".join(sorted(catalog.profile_names()))
        raise ValueError(f"Unknown doctor profile {name!r}; expected one of: {known}") from exc
    return DoctorProfile(name=name, components=components)


def collect_profile_components(
    collectors: dict[str, ComponentCollector],
    *,
    profile_name: str = "core",
    parallel: bool = False,
    max_workers: int | None = None,
) -> dict[str, dict[str, Any]]:
    profile = doctor_profile(profile_name)
    if parallel and len(profile.components) > 1:
        workers = max_workers or min(8, len(profile.components))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                component: executor.submit(collectors[component])
                for component in profile.components
            }
            reports: dict[str, dict[str, Any]] = {}
            try:
                for component in profile.components:
                    reports[component] = futures[component].result()
            except BaseException:
                for future in futures.values():
                    future.cancel()
                raise
            return reports
    reports: dict[str, dict[str, Any]] = {}
    for component in profile.components:
        collector = collectors[component]
        reports[component] = collector()
    return reports
