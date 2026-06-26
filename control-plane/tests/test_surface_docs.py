from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_readme_surface_contract_uses_owner_local_full_mcp_as_healthy_default() -> None:
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    surface_start = readme.index("## Surface Contract")
    release_start = readme.index("## Release Gate")
    surface_section = readme[surface_start:release_start]

    assert "owner_local_full_mcp" in surface_section
    assert "TELEGRAM_MCP_TOOL_PROFILE=default" in surface_section
    assert "is not a restricted profile" in surface_section
    assert "must not expose raw send/reply" not in surface_section


def test_operator_workflows_do_not_claim_default_profile_is_restricted() -> None:
    text = (REPO_ROOT / "docs/operator-workflows.md").read_text(encoding="utf-8")

    assert "owner_local_full_mcp" in text
    assert "TELEGRAM_MCP_TOOL_PROFILE=default" not in text
    assert "TELEGRAM_MCP_TOOL_PROFILE=facade" in text
