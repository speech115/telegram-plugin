from __future__ import annotations

import json
from pathlib import Path

import telegram_control_plane.surface_contract as surface_contract
from telegram_control_plane.audits import audit_docs, audit_mcp_surface
from telegram_control_plane.paths import PLUGIN_SOURCE
from telegram_control_plane.surface_contract import (
    canonical_tool_name,
    evaluate_docs_surface_contract,
    evaluate_plugin_allowlist_contract,
    is_approved_facade_tool,
    is_unexpected_on_default_surface,
    is_unsafe_plugin_allowlist_tool,
    load_surface_contract_policy,
)
from telegram_control_plane.util import load_json


def test_surface_contract_policy_matches_task_shaped_allowlist() -> None:
    policy = load_surface_contract_policy(
        str(surface_contract.SURFACE_CONTRACT_PATH),
        str(surface_contract.WRITE_POLICY_PATH),
    )
    assert policy.active_profile == "owner_local_full_mcp"
    assert "telegram_send" in policy.owner_local_required_tools
    assert "delete_messages" in policy.owner_local_direct_write_tools
    assert policy.owner_local_direct_write_tools_allowed is True
    assert policy.owner_local_plugin_allowlists_allowed is False
    assert "telegram_read" in policy.approved_facade_tools
    assert "telegram_search" in policy.approved_facade_tools
    assert "telegram_confirmed_send" in policy.confirmed_write_facade_tools
    assert "send_dialog_message" not in policy.approved_facade_tools
    assert policy.legacy_tool_aliases["read_today_dialog"] == "telegram_read"
    assert len(policy.approved_facade_tools) == 16


def test_canonical_tool_name_resolves_legacy_aliases() -> None:
    assert canonical_tool_name("read_today_dialog") == "telegram_read"
    assert canonical_tool_name("telegram_read") == "telegram_read"


def test_default_surface_classification_table() -> None:
    annotations = {"read_dialog": "readonly", "send_dialog_message": "additive"}
    cases = [
        ("telegram_read", False),
        ("telegram_confirmed_send", False),
        ("send_file", True),
        ("send_dialog_message", True),
        ("delete_messages", True),
        ("read_dialog", False),
    ]
    for tool, expected_unexpected in cases:
        assert is_unexpected_on_default_surface(tool, annotations) is expected_unexpected


def test_plugin_allowlist_rejects_non_facade_and_raw_write() -> None:
    annotations: dict[str, str] = {}
    assert is_unsafe_plugin_allowlist_tool("telegram_read", annotations) is False
    assert is_unsafe_plugin_allowlist_tool("delete_messages", annotations) is True
    assert is_unsafe_plugin_allowlist_tool("send_file", annotations) is True


def test_legacy_alias_does_not_expand_approved_set() -> None:
    assert is_approved_facade_tool("read_today_dialog") is False
    assert is_approved_facade_tool("telegram_read") is True


def test_surface_contract_policy_reloads_from_fixture(tmp_path: Path) -> None:
    policy_path = tmp_path / "surface-contract.json"
    policy_path.write_text(
        json.dumps(
            {
                "default_profile": {
                    "approved_facade_tools": ["telegram_read"],
                    "confirmed_write_facade_tools": [],
                    "deprecated_doc_tools": ["list_chats"],
                    "legacy_tool_aliases": {},
                    "full_profile_additive_tools": [],
                }
            }
        ),
        encoding="utf-8",
    )
    surface_contract.clear_policy_cache()
    policy = load_surface_contract_policy(str(policy_path), str(tmp_path / "missing.json"))

    assert policy.approved_facade_tools == frozenset({"telegram_read"})
    surface_contract.clear_policy_cache()


def test_plugin_allowlist_matches_surface_contract_policy() -> None:
    plugin_mcp = load_json(PLUGIN_SOURCE / ".mcp.json") or {}
    servers = plugin_mcp.get("mcpServers")
    assert isinstance(servers, dict)
    assert {"telegram-main", "telegram-pl"} <= set(servers)
    for server in servers.values():
        assert isinstance(server, dict)
        assert "allowedTools" not in server
        assert "allowTools" not in server
        assert isinstance(server.get("url"), str)


def test_agents_md_surface_tool_count_matches_policy() -> None:
    agents = (Path(__file__).resolve().parents[1] / "AGENTS.md").read_text(encoding="utf-8")
    findings = evaluate_docs_surface_contract(doc_name="AGENTS.md", text=agents)
    assert not any(item["id"] == "stale_surface_tool_count_in_docs" for item in findings)


def test_docs_audit_flags_wrong_surface_tool_count(monkeypatch, tmp_path: Path) -> None:
    readme = tmp_path / "README.md"
    readme.write_text("Default MCP surface (99 tools)\n", encoding="utf-8")
    monkeypatch.setattr(
        "telegram_control_plane.audits.DOC_AUDIT_PATHS",
        (readme,),
    )
    monkeypatch.setattr(
        "telegram_control_plane.audits.plugin_source_version",
        lambda: "0.1.10",
    )

    report = audit_docs()

    assert report["status"] == "fail"
    assert any(item["id"] == "stale_surface_tool_count_in_docs" for item in report["findings"])


def test_mcp_surface_flags_plugin_allowlist_drift(monkeypatch) -> None:
    import telegram_control_plane.audits as audits

    original_load_json = audits.load_json

    def fake_load_json(path: Path):
        if str(path).endswith("/.mcp.json"):
            return {"mcpServers": {"telegram-local": {"allowedTools": ["telegram_read"]}}}
        return original_load_json(path)

    monkeypatch.setattr(audits, "load_json", fake_load_json)

    report = audit_mcp_surface()

    assert report["status"] == "fail"
    assert any(
        item["id"] == "mcp_endpoint_has_legacy_allowlist" for item in report["findings"]
    )


def test_mcp_surface_includes_surface_contract_summary() -> None:
    report = audit_mcp_surface(include_live_probe=False)
    assert report["status"] == "ok"
    assert report["surface_mode"] == "owner_local_full_mcp"
    assert report["active_surface_tools"] == report["default_surface_tools"]
    assert "owner_local_full_mcp" in report["compatibility_note"]
    assert "telegram_send" in report["required_full_surface_tools"]
    assert "delete_messages" in report["default_surface_tools"]
    assert "delete_messages" in report["legacy_default_surface_evaluation"]["unexpected_write_or_destructive_tools"]
    assert report["missing_required_full_surface_tools"] == []
    assert report["surface_contract"]["active_profile"] == "owner_local_full_mcp"
    assert report["surface_contract"]["policy_path"].endswith("surface-contract.json")


def test_context_describes_owner_local_full_surface() -> None:
    root = Path(__file__).resolve().parents[1]
    context = (root / "CONTEXT.md").read_text(encoding="utf-8")
    mcp_surface = (root / "docs/agents/mcp-surface.md").read_text(encoding="utf-8")

    assert "owner_local_full_mcp" in context
    assert "owner_local_full_mcp" in mcp_surface
    assert "restricted tool profile" not in context
    assert "Legacy facade allowlist" in context
