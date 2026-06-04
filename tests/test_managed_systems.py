from __future__ import annotations

import telegram_control_plane.managed_systems as managed_systems
from telegram_control_plane.audits import audit_managed_systems
from telegram_control_plane.managed_systems import (
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
    assert system_path("telegram-mcp") == MCP_REPO


def test_managed_systems_policy_has_topology_bindings() -> None:
    policy = load_managed_systems_policy(str(MANAGED_SYSTEMS_PATH))
    bindings = policy["topology"]["bindings"]
    assert bindings["mcp_repo"] == "telegram-mcp"
    assert len(bindings) >= 10


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


def test_shell_exports_include_mcp_repo() -> None:
    exports = managed_systems.shell_exports()
    assert 'export TELEGRAM_MCP_REPO="' in exports
    assert str(MCP_REPO) in exports