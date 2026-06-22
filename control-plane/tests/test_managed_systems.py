from __future__ import annotations

import telegram_control_plane.managed_systems as managed_systems
from telegram_control_plane.audits import audit_managed_systems
from telegram_control_plane.managed_systems import (
    ControlPlaneTopology,
    MANAGED_SYSTEMS_PATH,
    evaluate_managed_systems,
    load_managed_systems_policy,
    resolve_topology,
    system_path,
)
from telegram_control_plane.paths import (
    CONTROL_ROOT,
    MCP_REPO,
    MIRROR_RUNTIME_ROOT,
    PLUGIN_SOURCE,
    TELECRAWL_DEFAULT_DB,
)


def test_topology_resolves_core_bindings() -> None:
    topology = resolve_topology()
    assert topology["control_root"] == CONTROL_ROOT
    assert topology["mcp_repo"] == MCP_REPO
    assert topology["plugin_source"] == PLUGIN_SOURCE
    assert topology["mirror_runtime_root"] == MIRROR_RUNTIME_ROOT
    assert topology["telecrawl_default_db"] == TELECRAWL_DEFAULT_DB


def test_system_path_matches_policy_entry() -> None:
    assert system_path("telegram-mcp-env") == MCP_REPO / ".env"


def test_control_plane_topology_resolves_derived_paths_with_fixture_home(tmp_path) -> None:
    control = tmp_path / "control"
    mcp = tmp_path / "mcp"
    policy = {
        "systems": [
            {"id": "control", "role": "control_plane", "path": str(control)},
            {"id": "mcp", "role": "live_mcp_backend", "path": str(mcp)},
        ],
        "topology": {
            "bindings": {"control_root": "control", "mcp_repo": "mcp"},
            "derived": {"generated_dir": "${control_root}/generated", "launchagents_dir": "$HOME/Library/LaunchAgents"},
        },
    }

    topology = ControlPlaneTopology(policy=policy, home=tmp_path / "home")
    resolved = topology.resolve()

    assert topology.system_path("mcp") == mcp
    assert resolved["generated_dir"] == control / "generated"
    assert resolved["launchagents_dir"] == tmp_path / "home" / "Library/LaunchAgents"


def test_topology_prefers_environment_overrides(monkeypatch, tmp_path) -> None:
    control = tmp_path / "portable-control"
    mcp = tmp_path / "portable-mcp"
    policy = {
        "systems": [
            {"id": "telegram-control-plane", "role": "control_plane", "path": "/old/control"},
            {"id": "telegram-mcp", "role": "live_mcp_backend", "path": "/old/mcp"},
        ],
        "topology": {
            "bindings": {"control_root": "telegram-control-plane", "mcp_repo": "telegram-mcp"},
            "derived": {"generated_dir": "${control_root}/generated"},
        },
    }
    monkeypatch.setenv("TELEGRAM_CONTROL_PLANE_ROOT", str(control))
    monkeypatch.setenv("TELEGRAM_MCP_REPO", str(mcp))

    topology = ControlPlaneTopology(policy=policy)

    assert topology.system_path("telegram-mcp") == mcp
    assert topology.resolve()["control_root"] == control
    assert topology.resolve()["mcp_repo"] == mcp
    assert topology.resolve()["generated_dir"] == control / "generated"


def test_control_plane_topology_blocks_unknown_binding() -> None:
    topology = ControlPlaneTopology(
        policy={
            "systems": [{"id": "control", "path": "/tmp/control"}],
            "topology": {"bindings": {"missing": "does-not-exist"}, "derived": {}},
        }
    )

    try:
        topology.resolve()
    except KeyError as exc:
        assert "unknown system" in str(exc)
    else:
        raise AssertionError("expected unknown topology binding to fail")


def test_managed_systems_policy_has_topology_bindings() -> None:
    policy = load_managed_systems_policy(str(MANAGED_SYSTEMS_PATH))
    assert set(policy["topology"]["bindings"]) >= {
        "control_root",
        "mcp_repo",
        "plugin_source",
        "mirror_runtime_root",
        "telecrawl_default_db",
    }
    assert {item["id"] for item in policy["systems"]} >= {
        "telegram-control-plane",
        "telegram-mcp",
        "telegram-plugin-package",
        "telegram-plugin-source",
        "telegram-plugin-cache",
        "telegram-live-skill",
        "telegram-local-mirror-skill",
        "telegram-mirror",
        "telegram-mirror-runtime",
        "telegram-mirror-compat-alias",
        "telecrawl-archive-wrapper",
        "telecrawl-fast-db",
        "telegram-main-session-dir",
        "telegram-pl-session-dir",
        "telegram-mcp-env",
    }


def test_evaluate_managed_systems_reports_missing_path(monkeypatch) -> None:
    policy = {
        "systems": [
            {
                "id": "telegram-mirror",
                "role": "mirror_recovery_candidate",
                "path": "/definitely/missing/telegram-mirror",
                "expected_kind": "directory",
                "deletion_protection": "blocking",
            }
        ],
        "topology": {"bindings": {}, "derived": {}},
        "deletion_policy": {},
    }

    monkeypatch.setattr(managed_systems, "load_managed_systems_policy", lambda *_a, **_k: policy)

    report = evaluate_managed_systems(policy=policy)

    assert report["status"] == "fail"
    assert any(item["id"] == "managed_system_missing" for item in report["findings"])


def test_audit_managed_systems_uses_managed_systems_module(monkeypatch) -> None:
    policy = {
        "systems": [
            {
                "id": "telegram-plugin-cache",
                "role": "installed_plugin_cache",
                "path": "/definitely/missing/telegram-plugin-cache",
                "expected_kind": "directory",
                "deletion_protection": "warn",
            }
        ],
        "topology": {"bindings": {}, "derived": {}},
        "deletion_policy": {},
    }

    monkeypatch.setattr(managed_systems, "load_managed_systems_policy", lambda *_a, **_k: policy)

    report = audit_managed_systems()

    assert report["status"] == "warn"
    assert report["summary"]["missing"] == 1


def test_evaluate_managed_systems_downgrades_local_paths_in_portable_mode(monkeypatch, tmp_path) -> None:
    control = CONTROL_ROOT
    mcp = tmp_path / "mcp"
    mcp.mkdir()
    (mcp / "README.md").write_text("", encoding="utf-8")
    policy = {
        "systems": [
            {
                "id": "telegram-control-plane",
                "role": "control_plane",
                "path": "/Users/sereja/Projects/tools/telegram/control-plane",
                "expected_kind": "directory",
                "deletion_protection": "blocking",
            },
            {
                "id": "telegram-mcp",
                "role": "live_mcp_backend",
                "path": "/Users/sereja/Projects/families/telegram/telegram-digest/telegram-mcp",
                "expected_kind": "directory",
                "deletion_protection": "blocking",
            },
            {
                "id": "telegram-live-skill",
                "role": "runtime_skill_facade",
                "path": "/Users/sereja/.agents/skills/telegram",
                "expected_kind": "symlink",
                "deletion_protection": "blocking",
            },
        ],
        "topology": {
            "bindings": {
                "control_root": "telegram-control-plane",
                "mcp_repo": "telegram-mcp",
                "live_skill": "telegram-live-skill",
            },
            "derived": {},
        },
    }
    monkeypatch.setenv("TELEGRAM_CI_PORTABLE", "1")
    monkeypatch.setenv("TELEGRAM_CONTROL_PLANE_ROOT", str(control))
    monkeypatch.setenv("TELEGRAM_MCP_REPO", str(mcp))
    monkeypatch.setenv("TELEGRAM_LIVE_SKILL", str(tmp_path / "missing-live-skill"))

    report = evaluate_managed_systems(policy=policy)

    assert report["status"] == "warn"
    assert not any(finding["severity"] == "blocking" for finding in report["findings"])


def test_shell_exports_include_mcp_repo() -> None:
    exports = managed_systems.shell_exports()
    assert 'export TELEGRAM_MCP_REPO="' in exports
    assert str(MCP_REPO) in exports


def test_hot_path_shell_exports_are_policy_backed_snapshot() -> None:
    shell = (MANAGED_SYSTEMS_PATH.parents[1] / "bin/telegram-env.sh").read_text(encoding="utf-8")
    for name in resolve_topology():
        assert f"TELEGRAM_{name.upper()}" in shell
