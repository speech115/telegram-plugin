"""Catalog of public commands and doctor components.

This is the source-of-truth module for command names, component ids, and profile
membership. Older modules expose compatibility adapters for callers.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

LEVELS = ("daily", "live", "mirror", "drilldown", "maintenance", "release")
SAFETIES = ("read-only", "mutating", "guarded")


@dataclass(frozen=True)
class CommandSpec:
    name: str
    purpose: str
    level: str
    safety: str
    example: str
    component: str | None = None


@dataclass(frozen=True)
class ComponentSpec:
    id: str
    profiles: tuple[str, ...]
    command_name: str | None = None


COMMAND_SPECS: tuple[CommandSpec, ...] = (
    CommandSpec(
        name="telegram-status",
        purpose="Human-readable core health summary",
        level="daily",
        safety="read-only",
        example="./bin/telegram-status",
    ),
    CommandSpec(
        name="telegram-doctor",
        purpose="Core-profile doctor; fails closed on blocking defects",
        level="daily",
        safety="read-only",
        example="./bin/telegram-doctor --json",
    ),
    CommandSpec(
        name="tgc",
        purpose="Agent entrypoint: `tgc next` (what to do now), `tgc commands --json` (this registry)",
        level="daily",
        safety="read-only",
        example="./bin/tgc next --json",
    ),
    CommandSpec(
        name="tg",
        purpose="Live Telegram CLI (read/search/today); first path for current reads",
        level="live",
        safety="read-only",
        example="tg read today <chat> --limit 30 --json",
    ),
    CommandSpec(
        name="telegram-fast-read-today",
        purpose="Direct MCP HTTP fast read for low-stakes 'today' tasks",
        level="live",
        safety="read-only",
        example="./bin/telegram-fast-read-today me --limit 1",
        component="fast_read_adapter",
    ),
    CommandSpec(
        name="telegram-mirror-fast",
        purpose="Mirror fast path: status/read/search over local exports only",
        level="mirror",
        safety="read-only",
        example="./bin/telegram-mirror-fast status --json",
        component="mirror_fast_status",
    ),
    CommandSpec(
        name="telegram-mcp-surface",
        purpose="Audit owner-local full MCP surface vs policy-required tools and account probes",
        level="drilldown",
        safety="read-only",
        example="./bin/telegram-mcp-surface --json",
        component="mcp_surface",
    ),
    CommandSpec(
        name="telegram-mcp-profiles",
        purpose="Audit MCP tool profiles (default/full/admin) configuration",
        level="drilldown",
        safety="read-only",
        example="./bin/telegram-mcp-profiles --json",
        component="mcp_profiles",
    ),
    CommandSpec(
        name="telegram-source-routing-audit",
        purpose="Audit live/mirror/archive source routing policy",
        level="drilldown",
        safety="read-only",
        example="./bin/telegram-source-routing-audit --json",
        component="source_routing",
    ),
    CommandSpec(
        name="telegram-source-route",
        purpose="Recommend live/mirror/archive source for a task intent",
        level="drilldown",
        safety="read-only",
        example="./bin/telegram-source-route 'что нового за сегодня' --json",
    ),
    CommandSpec(
        name="telegram-launchd-audit",
        purpose="Audit Telegram LaunchAgents (no secrets in plists, expected state)",
        level="drilldown",
        safety="read-only",
        example="./bin/telegram-launchd-audit --json",
        component="launchd",
    ),
    CommandSpec(
        name="telegram-session-audit",
        purpose="Audit Telegram session file locations and permissions",
        level="drilldown",
        safety="read-only",
        example="./bin/telegram-session-audit --json",
        component="sessions",
    ),
    CommandSpec(
        name="telegram-plugin-drift",
        purpose="Audit portable plugin package vs marketplace alias vs installed cache",
        level="drilldown",
        safety="read-only",
        example="./bin/telegram-plugin-drift --json",
        component="plugin_drift",
    ),
    CommandSpec(
        name="telegram-telemetry-status",
        purpose="Summarize MCP telemetry JSONL and Prometheus targets vs thresholds",
        level="drilldown",
        safety="read-only",
        example="./bin/telegram-telemetry-status --json",
        component="mcp_telemetry",
    ),
    CommandSpec(
        name="telegram-insights",
        purpose="Summarize actionable Telegram telemetry insights",
        level="drilldown",
        safety="read-only",
        example="./bin/telegram-insights --json",
    ),
    CommandSpec(
        name="telegram-telecrawl-status",
        purpose="Audit telecrawl archive gaps (archive evidence, not live truth)",
        level="drilldown",
        safety="read-only",
        example="./bin/telegram-telecrawl-status --json",
        component="telecrawl",
    ),
    CommandSpec(
        name="telegram-docs-audit",
        purpose="Audit agent docs/skill references for drift",
        level="drilldown",
        safety="read-only",
        example="./bin/telegram-docs-audit --json",
        component="docs",
    ),
    CommandSpec(
        name="telegram-managed-systems",
        purpose="Canonical inventory of Telegram repos, surfaces, and data roots",
        level="drilldown",
        safety="read-only",
        example="./bin/telegram-managed-systems --json",
        component="managed_systems",
    ),
    CommandSpec(
        name="telegram-mirror-audit",
        purpose="Audit mirror recovery candidate state",
        level="drilldown",
        safety="read-only",
        example="./bin/telegram-mirror-audit --json",
        component="telegram_mirror",
    ),
    CommandSpec(
        name="telegram-runtime-inventory",
        purpose="Audit runtime processes/daemons related to Telegram",
        level="drilldown",
        safety="read-only",
        example="./bin/telegram-runtime-inventory --json",
        component="runtime_inventory",
    ),
    CommandSpec(
        name="telegram-runtime-compat",
        purpose="Audit Telegram MCP runtime Telethon schema compatibility shims",
        level="drilldown",
        safety="read-only",
        example="./bin/telegram-runtime-compat --json",
        component="runtime_compat",
    ),
    CommandSpec(
        name="telegram-api-gap-audit",
        purpose="Audit Telegram API/Bot API capability gaps without enabling writes",
        level="drilldown",
        safety="read-only",
        example="./bin/telegram-api-gap-audit --json",
        component="api_gap_audit",
    ),
    CommandSpec(
        name="telegram-maintenance-doctor",
        purpose="Broad estate audit (release/plugin/archive/telemetry/recovery)",
        level="maintenance",
        safety="read-only",
        example="./bin/telegram-maintenance-doctor --json",
    ),
    CommandSpec(
        name="telegram-repair-plan",
        purpose="Dry-run ordered repair plan; never applies changes",
        level="maintenance",
        safety="read-only",
        example="./bin/telegram-repair-plan --json",
    ),
    CommandSpec(
        name="telegram-feature-status",
        purpose="Refresh/check the canonical feature-status CSV from real doctor output",
        level="maintenance",
        safety="mutating",
        example="./bin/telegram-feature-status --json",
    ),
    CommandSpec(
        name="telegram-operator-status",
        purpose="Human-readable operator summary across live MCP, telemetry, docs, runtime compat, and feature CSV",
        level="maintenance",
        safety="read-only",
        example="./bin/telegram-operator-status",
    ),
    CommandSpec(
        name="telegram-regression-loop",
        purpose="Run regression gates in the safe sequential order; live gates require --include-live",
        level="release",
        safety="read-only",
        example="./bin/telegram-regression-loop --include-live --json",
    ),
    CommandSpec(
        name="telegram-repair-plan-apply",
        purpose="Apply only allowlisted safe repair steps; explicit maintenance task only",
        level="maintenance",
        safety="guarded",
        example="./bin/telegram-repair-plan-apply --json",
    ),
    CommandSpec(
        name="telegram-mirror-preflight",
        purpose="Gate before promoting mirror from recovery to runtime",
        level="maintenance",
        safety="read-only",
        example="./bin/telegram-mirror-preflight --json",
    ),
    CommandSpec(
        name="telegram-music-autoclean",
        purpose="Dry-run classifier for the personal music channel post-cleanup watcher",
        level="maintenance",
        safety="read-only",
        example="./bin/telegram-music-autoclean --json",
    ),
    CommandSpec(
        name="telegram-golden-read-smoke",
        purpose="Live read smoke over golden dialogs; release/live-smoke only",
        level="release",
        safety="read-only",
        example="./bin/telegram-golden-read-smoke --json",
        component="golden_read_smoke",
    ),
    CommandSpec(
        name="telegram-release-gate",
        purpose="RUN the bundled pre-release gates (tests, audits, smokes)",
        level="release",
        safety="read-only",
        example="./bin/telegram-release-gate",
    ),
    CommandSpec(
        name="telegram-release-gates",
        purpose="AUDIT release-gate configuration (does not run the gates)",
        level="release",
        safety="read-only",
        example="./bin/telegram-release-gates --json",
        component="release_gates",
    ),
    CommandSpec(
        name="telegram-agent-docs-sync",
        purpose="Sync skill references into MCP agent docs; restarts local daemons",
        level="maintenance",
        safety="mutating",
        example="./bin/telegram-agent-docs-sync --check",
        component="agent_docs_sync",
    ),
    CommandSpec(
        name="telegram-install-adapters",
        purpose="Audit portable adapter install state",
        level="maintenance",
        safety="read-only",
        example="./bin/telegram-install-adapters --json",
        component="install_adapters",
    ),
    CommandSpec(
        name="telegram-kit",
        purpose="Install/check local kit symlinks (tg on PATH)",
        level="maintenance",
        safety="mutating",
        example="./bin/telegram-kit --local",
    ),
)

CORE_COMPONENTS = ("mcp_surface",)

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
    "runtime_compat",
    "telecrawl",
)

PROFILE_COMPONENTS = {
    "core": CORE_COMPONENTS,
    "maintenance": MAINTENANCE_COMPONENTS,
}


class ControlPlaneCatalog:
    def __init__(
        self,
        *,
        commands: tuple[CommandSpec, ...] = COMMAND_SPECS,
        profile_components: dict[str, tuple[str, ...]] = PROFILE_COMPONENTS,
    ) -> None:
        self._commands = commands
        self._profile_components = profile_components
        self._by_name = {spec.name: spec for spec in commands}
        self._by_component = {
            spec.component: spec for spec in commands if spec.component is not None
        }
        self._components = self._build_components()

    @classmethod
    def default(cls) -> "ControlPlaneCatalog":
        return cls()

    def _build_components(self) -> dict[str, ComponentSpec]:
        profile_names_by_component: dict[str, list[str]] = {}
        for profile, components in self._profile_components.items():
            for component in components:
                profile_names_by_component.setdefault(component, []).append(profile)
        return {
            component: ComponentSpec(
                id=component,
                profiles=tuple(profiles),
                command_name=self._by_component[component].name if component in self._by_component else None,
            )
            for component, profiles in profile_names_by_component.items()
        }

    def commands(self) -> tuple[CommandSpec, ...]:
        return self._commands

    def command_by_name(self, name: str) -> CommandSpec | None:
        return self._by_name.get(name)

    def command_for_component(self, component: str) -> CommandSpec | None:
        return self._by_component.get(component)

    def profile_names(self) -> tuple[str, ...]:
        return tuple(self._profile_components)

    def profile_components(self, profile: str) -> tuple[str, ...]:
        return self._profile_components[profile]

    def component(self, component: str) -> ComponentSpec | None:
        return self._components.get(component)

    def registry_report(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "levels": list(LEVELS),
            "safeties": list(SAFETIES),
            "commands": [asdict(spec) for spec in self._commands],
        }
