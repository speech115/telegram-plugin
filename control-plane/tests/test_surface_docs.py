from __future__ import annotations

from pathlib import Path


def test_readme_surface_contract_uses_owner_local_full_mcp_as_healthy_default() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    surface_start = readme.index("## Surface Contract")
    release_start = readme.index("## Release Gate")
    surface_section = readme[surface_start:release_start]

    assert "owner_local_full_mcp" in surface_section
    assert "must not expose raw send/reply" not in surface_section
