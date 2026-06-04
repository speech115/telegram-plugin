from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from .paths import POLICY_DIR
from .util import load_json

WRITE_OR_DESTRUCTIVE_RE = re.compile(
    r"^(create|delete|demote|edit|forward|import|invite|leave|mark|promote|reply|send|set|update)_"
)
DOC_SURFACE_COUNT_RE = re.compile(r"Default MCP surface \((\d+) tools\)", re.IGNORECASE)
DOC_TOOL_NAME_RE = re.compile(r"`([a-z][a-z0-9_]+)`")
DOC_FACADE_TOOL_RE = re.compile(
    r"^(?:telegram_|resolve_|find_|collect_|prepare_|download_|read_|search_|"
    r"doctor_|send_|reply_|draft_|list_|get_me)"
)

SURFACE_CONTRACT_PATH = POLICY_DIR / "surface-contract.json"
WRITE_POLICY_PATH = POLICY_DIR / "write-policy.json"


@dataclass(frozen=True)
class SurfaceContractPolicy:
    approved_facade_tools: frozenset[str]
    confirmed_write_facade_tools: frozenset[str]
    deprecated_doc_tools: frozenset[str]
    legacy_tool_aliases: dict[str, str]
    full_profile_additive_tools: frozenset[str]


def _as_str_set(values: Any) -> frozenset[str]:
    if not isinstance(values, list):
        return frozenset()
    return frozenset(str(item) for item in values if isinstance(item, str))


def _as_alias_map(values: Any) -> dict[str, str]:
    if not isinstance(values, dict):
        return {}
    return {
        str(key): str(value)
        for key, value in values.items()
        if isinstance(key, str) and isinstance(value, str)
    }


@lru_cache(maxsize=4)
def load_surface_contract_policy(
    surface_contract_path: str,
    write_policy_path: str,
) -> SurfaceContractPolicy:
    payload = load_json(Path(surface_contract_path)) or {}
    profile = payload.get("default_profile")
    if not isinstance(profile, dict):
        profile = {}

    confirmed = _as_str_set(profile.get("confirmed_write_facade_tools"))
    if not confirmed:
        write_payload = load_json(Path(write_policy_path)) or {}
        default_profile = write_payload.get("default_mcp_profile")
        if isinstance(default_profile, dict):
            confirmed = _as_str_set(default_profile.get("confirmed_write_facade_tools"))

    return SurfaceContractPolicy(
        approved_facade_tools=_as_str_set(profile.get("approved_facade_tools")),
        confirmed_write_facade_tools=confirmed,
        deprecated_doc_tools=_as_str_set(profile.get("deprecated_doc_tools")),
        legacy_tool_aliases=_as_alias_map(profile.get("legacy_tool_aliases")),
        full_profile_additive_tools=_as_str_set(profile.get("full_profile_additive_tools")),
    )


def clear_policy_cache() -> None:
    load_surface_contract_policy.cache_clear()


def _policy() -> SurfaceContractPolicy:
    return load_surface_contract_policy(
        str(SURFACE_CONTRACT_PATH),
        str(WRITE_POLICY_PATH),
    )


def contract_summary() -> dict[str, Any]:
    policy = _policy()
    approved = policy.approved_facade_tools
    return {
        "policy_path": str(SURFACE_CONTRACT_PATH),
        "approved_facade_tool_count": len(approved),
        "confirmed_write_facade_tools": sorted(policy.confirmed_write_facade_tools),
        "deprecated_doc_tools": sorted(policy.deprecated_doc_tools),
        "legacy_tool_aliases": dict(sorted(policy.legacy_tool_aliases.items())),
        "full_profile_additive_tools": sorted(policy.full_profile_additive_tools),
    }


def approved_facade_tools() -> frozenset[str]:
    return _policy().approved_facade_tools


def confirmed_write_facade_tools() -> frozenset[str]:
    return _policy().confirmed_write_facade_tools


def deprecated_doc_tools() -> frozenset[str]:
    return _policy().deprecated_doc_tools


def canonical_tool_name(name: str) -> str:
    return _policy().legacy_tool_aliases.get(name, name)


def is_approved_facade_tool(name: str) -> bool:
    return name in approved_facade_tools()


def is_unexpected_on_default_surface(name: str, dialog_annotations: dict[str, str]) -> bool:
    if name in confirmed_write_facade_tools():
        return False
    if WRITE_OR_DESTRUCTIVE_RE.search(name):
        return True
    return dialog_annotations.get(name) not in {None, "readonly"}


def is_unsafe_plugin_allowlist_tool(name: str, dialog_annotations: dict[str, str]) -> bool:
    return not is_approved_facade_tool(name) or is_unexpected_on_default_surface(
        name, dialog_annotations
    )


def evaluate_default_surface_tools(
    tool_names: list[str],
    dialog_annotations: dict[str, str],
) -> dict[str, Any]:
    unexpected_write = [
        name
        for name in tool_names
        if is_unexpected_on_default_surface(name, dialog_annotations)
    ]
    non_facade = [name for name in tool_names if not is_approved_facade_tool(name)]
    return {
        "unexpected_write_or_destructive_tools": unexpected_write,
        "non_facade_tools": non_facade,
    }


def evaluate_plugin_allowlist_contract(allowlist: set[str]) -> dict[str, Any]:
    approved = approved_facade_tools()
    extra = sorted(allowlist - approved)
    missing = sorted(approved - allowlist)
    return {
        "matches_contract": not extra and not missing,
        "extra_tools": extra,
        "missing_tools": missing,
        "approved_facade_tool_count": len(approved),
    }


def evaluate_docs_surface_contract(*, doc_name: str, text: str) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    policy = _policy()
    expected_count = len(policy.approved_facade_tools)

    for match in DOC_SURFACE_COUNT_RE.finditer(text):
        mentioned = int(match.group(1))
        if mentioned != expected_count:
            findings.append(
                {
                    "id": "stale_surface_tool_count_in_docs",
                    "severity": "blocking",
                    "message": (
                        f"{doc_name} documents Default MCP surface as {mentioned} tools; "
                        f"surface-contract.json defines {expected_count}."
                    ),
                    "path": doc_name,
                    "mentioned_count": mentioned,
                    "expected_count": expected_count,
                }
            )

    for tool in sorted(policy.deprecated_doc_tools):
        if tool in text:
            findings.append(
                {
                    "id": "deprecated_default_surface_tool_in_docs",
                    "severity": "blocking",
                    "message": (
                        f"{doc_name} documents deprecated default-surface tool {tool!r}; "
                        "update examples to facade tools."
                    ),
                    "path": doc_name,
                    "tool": tool,
                }
            )

    if doc_name == "AGENTS.md":
        documented_tools = {
            name
            for name in DOC_TOOL_NAME_RE.findall(text)
            if name not in policy.legacy_tool_aliases
            and DOC_FACADE_TOOL_RE.match(name)
        }
        unknown_tools = sorted(
            name
            for name in documented_tools
            if name not in policy.approved_facade_tools
            and name not in policy.full_profile_additive_tools
            and name not in policy.confirmed_write_facade_tools
        )
        if unknown_tools:
            findings.append(
                {
                    "id": "unknown_default_surface_tool_in_docs",
                    "severity": "blocking",
                    "message": (
                        f"{doc_name} documents tool names outside surface-contract.json: "
                        f"{', '.join(unknown_tools)}."
                    ),
                    "path": doc_name,
                    "tools": unknown_tools,
                }
            )

    return findings