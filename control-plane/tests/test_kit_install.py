from __future__ import annotations

from pathlib import Path

from telegram_control_plane.kit_install import plan_local_install


def test_plan_local_install_symlinks_kit_tg_wrapper(
    monkeypatch, tmp_path: Path
) -> None:
    control = tmp_path / "control"
    mcp = tmp_path / "mcp"
    plugin = control / "generated" / "telegram-plugin-package"
    skill = plugin / "skills" / "telegram"
    skill.mkdir(parents=True)
    wrapper = control / "bin" / "tg"
    wrapper.parent.mkdir(parents=True)
    wrapper.write_text("#!/bin/sh\ntrue\n", encoding="utf-8")
    wrapper.chmod(0o755)
    mcp_tg = mcp / "bin" / "tg"
    mcp_tg.parent.mkdir(parents=True)
    mcp_tg.write_text("#!/bin/sh\ntrue\n", encoding="utf-8")

    live_skill = tmp_path / ".agents" / "skills" / "telegram"
    monkeypatch.setattr("telegram_control_plane.kit_install.CONTROL_ROOT", control)
    monkeypatch.setattr("telegram_control_plane.kit_install.MCP_REPO", mcp)
    monkeypatch.setattr("telegram_control_plane.kit_install.PLUGIN_PACKAGE", plugin)
    monkeypatch.setattr("telegram_control_plane.kit_install.LIVE_SKILL", live_skill)
    monkeypatch.setattr("telegram_control_plane.kit_install.Path.home", lambda: tmp_path)

    result = plan_local_install(dry_run=True)
    assert result.status == "ok"
    tg_action = next(item for item in result.actions if item.get("path", "").endswith("/bin/tg"))
    assert tg_action["target"] == str(wrapper)