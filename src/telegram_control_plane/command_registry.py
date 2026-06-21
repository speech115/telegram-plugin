"""Single source of truth for every public control-plane command.

Every executable in ``bin/`` (except sourced helpers) must be registered here.
``tests/test_command_registry.py`` fails closed when a wrapper and the registry
drift apart, and when AGENTS.md stops documenting a daily/live command.
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
    # Doctor component this command drills into, if any.
    component: str | None = None


COMMAND_REGISTRY: tuple[CommandSpec, ...] = (
    # Daily health.
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
    # Live Telegram reads.
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
    # Mirror fast path.
    CommandSpec(
        name="telegram-mirror-fast",
        purpose="Mirror fast path: status/read/search over local exports only",
        level="mirror",
        safety="read-only",
        example="./bin/telegram-mirror-fast status --json",
        component="mirror_fast_status",
    ),
    # Drill-down audits (run only after doctor points at the component).
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
    # Maintenance / release.
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

_BY_COMPONENT = {
    spec.component: spec for spec in COMMAND_REGISTRY if spec.component is not None
}
_BY_NAME = {spec.name: spec for spec in COMMAND_REGISTRY}


def command_for_component(component: str) -> CommandSpec | None:
    return _BY_COMPONENT.get(component)


def command_by_name(name: str) -> CommandSpec | None:
    return _BY_NAME.get(name)


def registry_report() -> dict[str, Any]:
    return {
        "status": "ok",
        "levels": list(LEVELS),
        "safeties": list(SAFETIES),
        "commands": [asdict(spec) for spec in COMMAND_REGISTRY],
    }
