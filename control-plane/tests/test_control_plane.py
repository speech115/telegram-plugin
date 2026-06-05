from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import telegram_control_plane.audits as audits
from telegram_control_plane.audits import (
    _dialog_annotation_map,
    _imported_tool_names,
    audit_docs,
    audit_managed_systems,
    audit_mirror_preflight,
    audit_mcp_surface,
    audit_plugin_drift,
    build_registry,
)
import telegram_control_plane.planner as planner
from telegram_control_plane.audit_remediation import apply_repair_plan, build_repair_plan
from telegram_control_plane import audit_remediation as remediation
from telegram_control_plane.paths import CONTROL_ROOT, MCP_REPO, PLUGIN_SOURCE


def test_imported_tool_names_excludes_register_aliases(tmp_path: Path) -> None:
    source = tmp_path / "__init__.py"
    source.write_text(
        "from .x import send_message, read_dialog, register as register_x\n"
        "from .y import register as register_y, create_channel\n",
        encoding="utf-8",
    )
    assert _imported_tool_names(source) == ["create_channel", "read_dialog", "send_message"]


def test_dialog_annotation_map_reads_facade_registration(tmp_path: Path) -> None:
    source = tmp_path / "dialog.py"
    source.write_text(
        "def register(mcp):\n"
        "    mcp.tool(annotations=READONLY)(tool_error_handler(read_dialog))\n"
        "    mcp.tool(annotations=ADDITIVE)(tool_error_handler(send_dialog_message))\n",
        encoding="utf-8",
    )
    assert _dialog_annotation_map(source) == {
        "read_dialog": "readonly",
        "send_dialog_message": "additive",
    }


def test_mcp_surface_is_clean_after_default_profile_hardening() -> None:
    report = audit_mcp_surface()
    assert report["status"] == "ok"
    assert "create_channel" not in report["default_surface_tools"]
    assert "send_dialog_message" not in report["default_surface_tools"]
    assert "send_file" not in report["default_surface_tools"]
    assert "telegram_confirmed_send" in report["default_surface_tools"]
    assert not report["unexpected_write_or_destructive_tools"]


def test_docs_audit_passes_for_current_control_plane_docs() -> None:
    report = audit_docs()
    assert report["status"] == "ok"
    assert report["findings"] == []


def test_docs_audit_flags_stale_plugin_version(monkeypatch, tmp_path: Path) -> None:
    readme = tmp_path / "README.md"
    readme.write_text("Aligned at local Telegram plugin version `0.1.0`.\n", encoding="utf-8")
    monkeypatch.setattr(audits, "DOC_AUDIT_PATHS", (readme,))
    monkeypatch.setattr(audits, "plugin_source_version", lambda: "0.1.9")

    report = audit_docs()

    assert report["status"] == "fail"
    assert any(item["id"] == "stale_plugin_version_in_docs" for item in report["findings"])


def test_docs_audit_flags_deprecated_default_surface_tool(monkeypatch, tmp_path: Path) -> None:
    readme = tmp_path / "README.md"
    readme.write_text("Use list_chats for smoke.\n", encoding="utf-8")
    monkeypatch.setattr(audits, "DOC_AUDIT_PATHS", (readme,))
    monkeypatch.setattr(audits, "plugin_source_version", lambda: "0.1.9")

    report = audit_docs()

    assert report["status"] == "fail"
    assert any(item["id"] == "deprecated_default_surface_tool_in_docs" for item in report["findings"])


def test_fast_read_adapter_is_registered_as_safe_first_path() -> None:
    report = audits.audit_fast_read_adapter()

    assert report["status"] == "ok"
    assert report["adapter"]["label"] == "tg"
    assert report["adapter"]["exists"] is True
    assert report["adapter"]["executable"] is True
    assert report["routing"]["cli"] == "tg"
    assert "simple_today_read" in report["routing"]["first_path_for"]
    assert report["routing"]["fallback"] == "live_mcp_facade"
    assert "tg_on_path" in report
    assert report["routing"]["codex_hot_path_doc"] == (
        "generated/adapters/codex/telegram-codex-entry.md"
    )


def test_fast_read_adapter_calls_task_shaped_tool() -> None:
    wrapper = (Path(__file__).resolve().parents[1] / "bin" / "telegram-fast-read-today").read_text(
        encoding="utf-8"
    )
    module = (MCP_REPO / "src/telegram_mcp/fast_read_today.py").read_text(encoding="utf-8")

    assert "telegram_mcp.fast_read_today" in wrapper
    assert '"telegram_read"' in module
    assert '"read_today_dialog"' not in module


def test_registry_includes_fast_read_adapter_component() -> None:
    registry = build_registry()

    assert registry["summary"]["components"]["fast_read_adapter"] == "ok"
    adapters = registry["components"]["fast_read_adapter"]["adapters"]
    assert any(item.get("label") == "tg" and item.get("exists") for item in adapters)


def test_agent_docs_sync_audit_passes() -> None:
    report = audits.audit_agent_docs_sync()

    assert report["status"] == "ok", report.get("findings")


def test_release_gates_audit_passes() -> None:
    report = audits.audit_release_gates()

    assert report["status"] == "ok", report.get("findings")


def test_install_adapters_audit_is_portable() -> None:
    report = audits.audit_install_adapters()

    assert report["status"] == "ok", report.get("findings")
    assert report["planned_files"] >= 4


def test_registry_includes_docs_component() -> None:
    registry = build_registry()

    assert registry["summary"]["components"]["docs"] == "ok"
    assert registry["components"]["docs"]["plugin_version"] is not None


def test_telecrawl_audit_uses_fast_manifest_status(monkeypatch, tmp_path: Path) -> None:
    db = tmp_path / "telecrawl-fast.db"
    manifest = tmp_path / "telecrawl-fast.db.manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "source_kind": "archive_snapshot",
                "manifest_status": "complete",
                "coverage_claim": "full_verified_archive_snapshot",
                "import": {"last_complete_import_at": "2026-05-18T16:54:53Z"},
                "counts": {"chats": 2, "messages": 3, "newest_message": "2026-05-18T16:18:16Z"},
            }
        ),
        encoding="utf-8",
    )
    with sqlite3.connect(db) as conn:
        conn.executescript(
            """
            CREATE TABLE import_errors (
                chat_jid text,
                error_type text
            );
            INSERT INTO import_errors VALUES ('1', 'TimeoutError'), ('1', 'TimeoutError'), ('2', 'TypeNotFoundError');
            """
        )

    def fake_telecrawl_json(args: list[str], *, timeout: int = 90):
        assert args == ["accounts"]
        return {
            "ok": True,
            "accounts": [
                {"active": 1, "db_exists": True},
                {"active": 0, "db_exists": False},
            ],
        }

    import telegram_control_plane.telecrawl_gap as telecrawl_gap

    monkeypatch.setattr(audits, "TELECRAWL_DEFAULT_DB", db)
    monkeypatch.setattr(telecrawl_gap, "TELECRAWL_DEFAULT_DB", db)
    monkeypatch.setattr(audits, "_safe_read_telecrawl_json", fake_telecrawl_json)

    report = audits.audit_telecrawl()

    assert report["default_archive_status"]["read_strategy"] == "manifest_plus_import_errors"
    assert report["default_archive_status"]["source_kind"] == "archive_snapshot"
    assert report["default_archive_status"]["archive_ready"] is True
    assert report["default_archive_status"]["manifest_coverage_claim"] == "full_verified_archive_snapshot"
    assert report["default_archive_status"]["coverage_claim"] == "partial_archive_snapshot_with_known_gaps"
    assert report["freshness"]["last_complete_import_at"] == "2026-05-18T16:54:53Z"
    assert report["freshness"]["newest_message_at"] == "2026-05-18T16:18:16Z"
    assert any(item["id"] == "telecrawl_known_gaps" for item in report["findings"])
    assert not any(item["id"] == "telecrawl_active_archives_incomplete" for item in report["findings"])


def test_telecrawl_audit_warns_for_active_missing_archive(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(audits, "TELECRAWL_DEFAULT_DB", tmp_path / "missing.db")
    monkeypatch.setattr(
        audits,
        "_safe_read_telecrawl_json",
        lambda *args, **kwargs: {
            "ok": True,
            "accounts": [{"active": 1, "db_exists": False, "manifest_stale_or_missing": True}],
        },
    )

    report = audits.audit_telecrawl()

    assert any(item["id"] == "telecrawl_active_archives_incomplete" for item in report["findings"])


def test_telecrawl_access_denied_gaps_are_terminal_not_retryable(tmp_path: Path) -> None:
    db = tmp_path / "telecrawl-fast.db"
    with sqlite3.connect(db) as conn:
        conn.executescript(
            """
            CREATE TABLE import_errors (
                chat_jid text,
                error_type text
            );
            INSERT INTO import_errors VALUES ('1', 'ChannelPrivateError'), ('1', 'ChannelPrivateError');
            INSERT INTO import_errors VALUES ('2', 'TimeoutError');
            """
        )

    from telegram_control_plane.telecrawl_gap import import_gaps

    gaps = import_gaps(db, non_retryable_error_types={"ChannelPrivateError"})

    assert gaps["errors"] == 3
    assert gaps["retryable_errors"] == 1
    assert gaps["terminal_errors"] == 2
    assert gaps["has_retryable_gaps"] is True
    assert gaps["has_terminal_gaps"] is True
    assert gaps["retryable_error_summary"] == [{"error_type": "TimeoutError", "chats": 1, "attempts": 1}]
    assert gaps["terminal_error_summary"] == [{"error_type": "ChannelPrivateError", "chats": 1, "attempts": 2}]
    assert gaps["retry_policy"]["do_not_retry_terminal_gaps"] is True


def test_mirror_audit_reads_external_runtime_root(monkeypatch, tmp_path: Path) -> None:
    checkout = tmp_path / "telegram-mirror"
    runtime = tmp_path / "runtime" / "telegram-mirror"
    (checkout / ".git").mkdir(parents=True)
    (checkout / "data").mkdir()
    for name in ["AGENTS.md", "RECOVERY.md", "PROVENANCE.md"]:
        (checkout / name).write_text("", encoding="utf-8")
    (runtime / "data" / "telegram_sync").mkdir(parents=True)
    (runtime / "runtime" / "ingest" / "telegram" / "exports").mkdir(parents=True)
    (runtime / "data" / "telegram_mirror_watch_prime.session").write_text("", encoding="utf-8")
    (runtime / "data" / "telegram_sync" / "watch_progress_prime.json").write_text("{}", encoding="utf-8")
    export_messages = runtime / "runtime" / "ingest" / "telegram" / "exports" / "prime" / "messages_raw.jsonl"
    export_messages.parent.mkdir(parents=True)
    export_messages.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(audits, "MIRROR_ROOT", checkout)
    monkeypatch.setattr(audits, "MIRROR_RUNTIME_ROOT", runtime)
    monkeypatch.setattr(audits, "MIRROR_LEGACY_ALIAS", tmp_path / "missing-alias")
    monkeypatch.setattr(audits, "load_json", lambda path: {"classification": "mirror-recovery"})
    monkeypatch.setattr(
        audits,
        "run_json",
        lambda *args, **kwargs: {"channels": [{"retained": True, "export_folder": "prime"}]},
    )

    report = audits.audit_mirror()

    finding_ids = {item["id"] for item in report["findings"]}
    assert "mirror_runtime_exports_missing" not in finding_ids
    assert "mirror_runtime_sessions_in_tree" not in finding_ids
    assert report["runtime_root"] == str(runtime)
    assert report["runtime_state"]["runtime_root_exists"] is True
    assert report["runtime_state"]["runtime_exports_exists"] is True
    assert report["runtime_state"]["sessions"] == [str(runtime / "data" / "telegram_mirror_watch_prime.session")]
    assert report["runtime_state"]["ledgers"] == [
        str(runtime / "data" / "telegram_sync" / "watch_progress_prime.json")
    ]
    assert report["runtime_state"]["export_coverage"] == {
        "source": "allowlist_report",
        "export_root": str(runtime / "runtime" / "ingest" / "telegram" / "exports"),
        "expected_count": 1,
        "ready_count": 1,
        "missing_count": 0,
        "missing": [],
    }


def test_mirror_preflight_externalizes_only_recovery_sessions(monkeypatch, tmp_path: Path) -> None:
    runtime = tmp_path / "runtime" / "telegram-mirror"
    (runtime / "runtime" / "ingest" / "telegram" / "exports").mkdir(parents=True)
    monkeypatch.setattr(audits, "MIRROR_RUNTIME_ROOT", runtime)
    monkeypatch.setattr(audits, "MIRROR_ROOT", tmp_path / "telegram-mirror")
    monkeypatch.setattr(
        audits,
        "audit_mirror",
        lambda: {
            "status": "warn",
            "classification": "mirror-recovery",
            "findings": [],
            "runtime_state": {
                "recovery_sessions": [],
                "sessions": ["runtime.session"],
                "ledgers": ["watch_progress.json"],
                "runtime_root_exists": True,
                "runtime_exports_exists": True,
            },
        },
    )
    monkeypatch.setattr(audits, "run_json", lambda *args, **kwargs: {"policy_exists": True, "registry": {"mirrors_count": 1}})
    monkeypatch.setattr(audits, "audit_launchd", lambda: {"loaded_jobs": {}})
    monkeypatch.setattr(audits, "audit_sessions", lambda: {"status": "ok", "findings": []})

    report = audit_mirror_preflight()
    gates = {gate["id"]: gate for gate in report["gates"]}

    assert gates["session_externalization"]["status"] == "ok"
    assert gates["session_externalization"]["evidence"]["session_count_in_tree"] == 0
    assert gates["runtime_exports"]["status"] == "ok"
    assert gates["runtime_exports"]["evidence"]["path"] == str(runtime / "runtime" / "ingest" / "telegram" / "exports")


def test_mcp_surface_blocks_unsafe_plugin_allowlist(monkeypatch) -> None:
    original_load_json = audits.load_json

    def fake_load_json(path: Path):
        if str(path).endswith("/.mcp.json"):
            return {"mcpServers": {"telegram-local": {"allowedTools": ["delete_messages"]}}}
        return original_load_json(path)

    monkeypatch.setattr(audits, "load_json", fake_load_json)

    report = audit_mcp_surface()

    assert report["status"] == "fail"
    assert any(item["id"] == "mcp_endpoint_unsafe_allowlist_tool" for item in report["findings"])


def test_plugin_package_has_no_private_runtime_artifacts() -> None:
    forbidden_names = {".env", "__pycache__"}
    forbidden_suffixes = {".session", ".pyc"}
    findings: list[str] = []

    for path in PLUGIN_SOURCE.rglob("*"):
        relative = path.relative_to(PLUGIN_SOURCE)
        if path.name in forbidden_names or path.suffix in forbidden_suffixes:
            findings.append(str(relative))
            continue
        if not path.is_file() or path.stat().st_size > 1_000_000:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if "/Users/sereja" in text:
            findings.append(f"{relative}: hardcoded private path")

    assert findings == []


def test_plugin_drift_uses_mcp_checker_tree_output(monkeypatch) -> None:
    monkeypatch.setattr(
        audits,
        "run_json",
        lambda *args, **kwargs: {
            "status": "installer_ready_drift",
            "installer_flow": {
                "safe_to_apply": True,
                "command": ["codex", "plugin", "remove", "telegram@sereja-local"],
            },
            "live_skill": {"sha256": "skill-sha"},
            "plugin_source_skill": {"sha256": "skill-sha"},
            "plugin_cache_skill": {"sha256": "skill-sha"},
            "plugin_source_skill_tree": {"sha256": "source-tree", "file_count": 9},
            "plugin_cache_skill_tree": {"sha256": "cache-tree", "file_count": 9},
            "plugin_source_package_tree": {"sha256": "source-package", "file_count": 18},
            "plugin_cache_package_tree": {"sha256": "cache-package", "file_count": 18},
            "tree_diff": {
                "plugin_source_vs_cache_skill_tree": {
                    "left_only": [],
                    "right_only": [],
                    "changed": ["references/facade-routing.md"],
                }
            },
        },
    )

    report = audit_plugin_drift()

    assert report["status"] == "warn"
    assert any(item["id"] == "plugin_cache_needs_materialization" for item in report["findings"])
    assert report["sha256"]["plugin_cache_skill"] == "skill-sha"
    assert report["tree_sha256"]["plugin_source_skill_tree"] == "source-tree"
    assert report["tree_sha256"]["plugin_cache_package"] == "cache-package"
    assert report["tree_file_counts"]["plugin_source_package"] == 18
    assert report["tree_diff"]["plugin_source_vs_cache_skill_tree"]["changed"] == [
        "references/facade-routing.md"
    ]


def test_launchd_blocks_malformed_plist(monkeypatch, tmp_path: Path) -> None:
    bad_plist = tmp_path / "com.sereja.telegram-bad.plist"
    bad_plist.write_text("not a plist", encoding="utf-8")
    monkeypatch.setattr(audits, "LAUNCHAGENTS_DIR", tmp_path)
    monkeypatch.setattr(audits, "_launchctl_labels", lambda: {})

    report = audits.audit_launchd()

    assert report["status"] == "fail"
    assert any(item["id"] == "launchd_plist_parse_error" for item in report["findings"])


def test_launchd_blocks_nonzero_launchctl(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(audits, "LAUNCHAGENTS_DIR", tmp_path)

    class Completed:
        returncode = 1
        stdout = ""
        stderr = "launchctl unavailable"

    monkeypatch.setattr(audits.subprocess, "run", lambda *args, **kwargs: Completed())

    report = audits.audit_launchd()

    assert report["status"] == "fail"
    assert any(item["id"] == "launchctl_list_failed" for item in report["findings"])


def test_launchd_blocks_paths_outside_allowed_roots(monkeypatch, tmp_path: Path) -> None:
    plist = tmp_path / "com.sereja.telegram-evil.plist"
    plist.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.sereja.telegram-evil</string>
  <key>ProgramArguments</key>
  <array><string>/tmp/evil/run.sh</string></array>
</dict>
</plist>
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(audits, "LAUNCHAGENTS_DIR", tmp_path)
    monkeypatch.setattr(audits, "_launchctl_labels", lambda: {})

    report = audits.audit_launchd()

    assert report["status"] == "fail"
    assert any(item["id"] == "launchd_path_outside_allowed_roots" for item in report["findings"])


def test_managed_systems_blocks_missing_protected_path(monkeypatch) -> None:
    import telegram_control_plane.managed_systems as managed_systems

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
    monkeypatch.setattr(
        managed_systems,
        "load_managed_systems_policy",
        lambda *_args, **_kwargs: policy,
    )

    report = audit_managed_systems()

    assert report["status"] == "fail"
    assert any(item["id"] == "managed_system_missing" for item in report["findings"])


def test_managed_systems_warns_for_missing_warn_only_path(monkeypatch) -> None:
    import telegram_control_plane.managed_systems as managed_systems

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
    monkeypatch.setattr(
        managed_systems,
        "load_managed_systems_policy",
        lambda *_args, **_kwargs: policy,
    )

    report = audit_managed_systems()

    assert report["status"] == "warn"
    assert report["summary"]["missing"] == 1


def test_managed_systems_blocks_wrong_directory_with_missing_markers(monkeypatch, tmp_path: Path) -> None:
    wrong_root = tmp_path / "telegram-mirror"
    wrong_root.mkdir()

    import telegram_control_plane.managed_systems as managed_systems

    policy = {
        "systems": [
            {
                "id": "telegram-mirror",
                "role": "mirror_recovery_candidate",
                "path": str(wrong_root),
                "expected_kind": "directory",
                "required_markers": ["AGENTS.md", "scripts/telegram_mirror_allowlist_report.py"],
                "deletion_protection": "blocking",
            }
        ],
        "topology": {"bindings": {}, "derived": {}},
        "deletion_policy": {},
    }
    monkeypatch.setattr(
        managed_systems,
        "load_managed_systems_policy",
        lambda *_args, **_kwargs: policy,
    )

    report = audit_managed_systems()

    assert report["status"] == "fail"
    assert any(item["id"] == "managed_system_marker_missing" for item in report["findings"])


def test_managed_systems_blocks_unexpected_symlink_target(monkeypatch, tmp_path: Path) -> None:
    expected = tmp_path / "expected"
    actual = tmp_path / "actual"
    link = tmp_path / "telegram"
    expected.mkdir()
    actual.mkdir()
    link.symlink_to(actual, target_is_directory=True)

    import telegram_control_plane.managed_systems as managed_systems

    policy = {
        "systems": [
            {
                "id": "telegram-plugin-source",
                "role": "local_marketplace_plugin_alias",
                "path": str(link),
                "expected_kind": "symlink",
                "expected_resolved": str(expected),
                "deletion_protection": "blocking",
            }
        ],
        "topology": {"bindings": {}, "derived": {}},
        "deletion_policy": {},
    }
    monkeypatch.setattr(
        managed_systems,
        "load_managed_systems_policy",
        lambda *_args, **_kwargs: policy,
    )

    report = audit_managed_systems()

    assert report["status"] == "fail"
    assert any(item["id"] == "managed_system_resolved_target_mismatch" for item in report["findings"])


def test_registry_persisted_snapshot_redacts_private_runtime_details(monkeypatch) -> None:
    private_components = {
        "plugin_drift": {"status": "ok", "findings": []},
        "mcp_surface": {"status": "ok", "findings": []},
        "mcp_profiles": {"status": "ok", "findings": [], "profiles": []},
        "launchd": {"status": "ok", "findings": []},
        "sessions": {
            "status": "ok",
            "findings": [],
            "sessions": [
                {
                    "path": "/Users/sereja/.telegram-mcp/session.session",
                    "exists": True,
                    "registered": True,
                    "runtime_allowed": True,
                    "schema_checked": False,
                    "lease_checked": False,
                }
            ],
            "policy": {
                "sessions": [
                    {
                        "path": "/Users/sereja/.telegram-mcp/session.session",
                        "account_key": "telegram-mcp-main",
                        "owner": "com.sereja.telegram-mcp-http",
                        "runtime_allowed": True,
                    }
                ]
            },
        },
        "telegram_mirror": {
            "status": "warn",
            "classification": "mirror-recovery",
            "findings": [],
            "runtime_state": {
                "sessions": ["/Users/sereja/Projects/tools/telegram-mirror/data/private.session"],
                "ledgers": [],
                "runtime_exports_exists": False,
            },
        },
        "telecrawl": {
            "status": "warn",
            "findings": [],
            "accounts": {
                "accounts": [
                    {
                        "account_key": "tg:7091037467",
                        "telegram_user_id": "7091037467",
                        "username": "CrwDdy",
                        "label": "Telegram @CrwDdy",
                        "tdata_path": "/Users/sereja/Library/Application Support/Telegram Desktop/tdata",
                        "db_path": "/Users/sereja/Projects/.artifacts/telecrawl/telecrawl-fast.db",
                        "manifest_path": "/Users/sereja/Projects/.artifacts/telecrawl/telecrawl-fast.db.manifest.json",
                        "active": 1,
                    }
                ]
            },
            "default_archive_status": {
                "archive_ready": True,
                "account": {
                    "account_key": "tg:7091037467",
                    "telegram_user_id": "7091037467",
                    "label": "Telegram @CrwDdy",
                },
            },
        },
        "managed_systems": {
            "status": "ok",
            "findings": [],
            "summary": {"registered": 1, "existing": 1},
            "systems": [
                {
                    "id": "telegram-mirror",
                    "path": "/Users/sereja/Projects/tools/telegram-mirror",
                    "exists": True,
                    "deletion_protection": "blocking",
                }
            ],
            "deletion_policy": {"default": "deny"},
        },
    }
    monkeypatch.setattr(audits, "_collect_components", lambda: private_components)

    registry = build_registry()

    encoded = json.dumps(registry, ensure_ascii=False)

    assert "/Users/sereja/.telegram-mcp/session.session" not in encoded
    assert "telegram_user_id" not in encoded
    assert "tdata_path" not in encoded
    assert "db_path" not in encoded
    assert "manifest_path" not in encoded
    assert "Telegram @" not in encoded
    assert "tg:7091037467" not in encoded


def test_registry_uses_allowlisted_component_schema(monkeypatch) -> None:
    monkeypatch.setattr(audits, "_collect_components", lambda: {
        "managed_systems": {
            "status": "ok",
            "findings": [],
            "summary": {"registered": 1, "existing": 1},
            "systems": [
                {
                    "id": "telegram-mirror",
                    "path": "/Users/sereja/Projects/tools/telegram-mirror",
                    "exists": True,
                    "deletion_protection": "blocking",
                }
            ],
            "deletion_policy": {"default": "deny"},
        },
        "plugin_drift": {"status": "ok", "findings": []},
        "mcp_surface": {"status": "ok", "findings": []},
        "mcp_profiles": {"status": "ok", "findings": [], "profiles": []},
        "launchd": {"status": "ok", "findings": []},
        "sessions": {
            "status": "ok",
            "findings": [],
            "sessions": [{"exists": True, "registered": True, "runtime_allowed": True}],
            "policy": {"sessions": [{"runtime_allowed": True}]},
        },
        "telegram_mirror": {
            "status": "warn",
            "classification": "mirror-recovery",
            "findings": [],
            "runtime_state": {"sessions": ["private.session"], "ledgers": ["ledger.json"], "runtime_exports_exists": False},
        },
        "telecrawl": {
            "status": "warn",
            "findings": [],
            "wrapper": "/bin/telecrawl-archive",
            "gap_policy": {"is_live": False},
            "accounts": {"accounts": [{"active": 1}, {"active": 0}]},
            "default_archive_status": {"archive_ready": True, "import_gaps": {"errors": 3}},
            "freshness": {"generated_at": "2026-06-04T00:00:00Z"},
        },
    })

    registry = build_registry()

    assert set(registry["components"]["sessions"]) == {"status", "findings", "summary", "policy_summary"}
    assert "sessions" not in registry["components"]["sessions"]
    assert "accounts" not in registry["components"]["telecrawl"]
    assert "default_archive_status" not in registry["components"]["telecrawl"]
    assert "gap_policy" in registry["components"]["telecrawl"]
    assert "runtime_state" not in registry["components"]["telegram_mirror"]
    assert "managed_systems" in registry["components"]


def test_registry_is_json_serializable_and_has_no_blocking_findings_after_policy(monkeypatch) -> None:
    components = {
        "plugin_drift": {"status": "ok", "findings": []},
        "managed_systems": {"status": "ok", "findings": []},
        "docs": {"status": "ok", "findings": [], "checked_paths": [], "plugin_version": "0.1.9"},
        "mcp_surface": {"status": "ok", "findings": []},
        "mcp_profiles": {"status": "ok", "findings": []},
        "launchd": {"status": "ok", "findings": []},
        "sessions": {"status": "ok", "findings": []},
        "telegram_mirror": {
            "status": "warn",
            "classification": "mirror-recovery",
            "findings": [{"id": "mirror_runtime_exports_missing", "severity": "warn"}],
        },
        "telecrawl": {
            "status": "warn",
            "findings": [{"id": "telecrawl_known_gaps", "severity": "warn"}],
        },
        "source_routing": {"status": "ok", "findings": []},
        "runtime_inventory": {"status": "ok", "findings": [], "summary": {}},
        "mcp_telemetry": {"status": "ok", "findings": []},
        "fast_read_adapter": {"status": "ok", "findings": []},
        "agent_docs_sync": {"status": "ok", "findings": []},
        "release_gates": {"status": "ok", "findings": []},
        "install_adapters": {"status": "ok", "findings": []},
    }
    monkeypatch.setattr(audits, "_collect_components", lambda: components)

    registry = build_registry()
    encoded = json.dumps(registry, ensure_ascii=False)

    assert encoded
    assert registry["status"] == "warn"
    assert registry["summary"]["blocking_findings"] == 0
    assert {
        "managed_systems",
        "docs",
        "plugin_drift",
        "mcp_surface",
        "launchd",
        "sessions",
        "telegram_mirror",
        "telecrawl",
        "source_routing",
        "runtime_inventory",
    }.issubset(registry["components"])


def test_repair_plan_surfaces_send_file_surface_repair(monkeypatch) -> None:
    monkeypatch.setattr(
        remediation,
        "build_registry",
        lambda: {
            "status": "fail",
            "summary": {"components": {"mcp_surface": "fail"}},
            "findings": [
                {
                    "component": "mcp_surface",
                    "id": "unexpected_write_tools",
                    "severity": "blocking",
                    "message": "Default MCP endpoint exposes write/destructive tools outside the approved facade.",
                    "tools": ["send_file"],
                }
            ],
            "components": {},
        },
    )

    plan = build_repair_plan()
    step = {item["id"]: item for item in plan["steps"]}["mcp-surface-allowlist"]

    assert step["status"] == "blocked_by_current_surface"
    assert "send_file" in step["reason"]
    assert step["apply_commands"] == [["python3", "-m", "pytest", "-q", "tests/test_registration.py"]]
    from telegram_control_plane.paths import MCP_REPO

    assert str(MCP_REPO / "src/telegram_mcp/tools/media_tools.py") in step["touched_paths"]


def test_repair_plan_is_ordered_and_dry_run_by_default(monkeypatch) -> None:
    monkeypatch.setattr(
        remediation,
        "build_registry",
        lambda: {
            "status": "warn",
            "summary": {
                "components": {
                    "managed_systems": "ok",
                    "plugin_drift": "ok",
                    "mcp_surface": "ok",
                    "launchd": "ok",
                    "sessions": "ok",
                    "telegram_mirror": "warn",
                    "telecrawl": "warn",
                }
            },
            "findings": [],
            "components": {},
        },
    )

    plan = build_repair_plan()
    assert plan["status"] == "ready"
    assert plan["safety"]["default_mode"] == "dry_run_only"
    assert plan["recommended_order"][0] == "managed-systems-inventory"
    by_id = {step["id"]: step for step in plan["steps"]}
    assert by_id["managed-systems-inventory"]["apply_commands"] == []
    assert by_id["plugin-cache-parity"]["verification_commands"]
    assert by_id["plugin-cache-parity"]["apply_commands"] == [
        ["codex", "plugin", "remove", "telegram@sereja-local"],
        ["codex", "plugin", "add", "telegram@sereja-local"],
    ]
    assert by_id["launchd-inventory-and-cold-mode"]["apply_commands"] == []


def test_repair_plan_surfaces_mirror_export_gap(monkeypatch) -> None:
    monkeypatch.setattr(
        remediation,
        "build_registry",
        lambda: {
            "status": "warn",
            "summary": {
                "components": {
                    "managed_systems": "ok",
                    "plugin_drift": "ok",
                    "mcp_surface": "ok",
                    "launchd": "ok",
                    "sessions": "ok",
                    "telegram_mirror": "warn",
                    "telecrawl": "ok",
                }
            },
            "findings": [{"component": "telegram_mirror", "id": "mirror_runtime_exports_missing", "severity": "warn"}],
            "components": {
                "telegram_mirror": {
                    "runtime_state_summary": {
                        "export_expected_count": 36,
                        "export_ready_count": 0,
                        "export_missing_count": 36,
                    }
                }
            },
        },
    )

    plan = build_repair_plan()
    by_id = {step["id"]: step for step in plan["steps"]}

    assert by_id["mirror-runtime-promotion-policy"]["status"] == "needs_runtime_exports"
    assert "0/36 ready, 36 missing" in by_id["mirror-runtime-promotion-policy"]["reason"]
    assert [
        str(CONTROL_ROOT / "bin/telegram-mirror-preflight"),
        "--json",
    ] in by_id["mirror-runtime-promotion-policy"]["dry_run_commands"]


def test_repair_plan_materialize_step_is_auto_apply_ready(monkeypatch) -> None:
    monkeypatch.setattr(
        remediation,
        "build_registry",
        lambda: {
            "status": "warn",
            "summary": {"components": {"plugin_drift": "warn"}},
            "findings": [
                {
                    "component": "plugin_drift",
                    "id": "plugin_cache_needs_materialization",
                    "severity": "warn",
                    "materialize_command": ["/tmp/materialize", "--json"],
                }
            ],
            "components": {},
        },
    )

    plan = build_repair_plan()
    by_id = {step["id"]: step for step in plan["steps"]}
    step = by_id["plugin-cache-materialize"]
    assert step["status"] == "ready_to_apply"
    assert step["auto_apply_allowed"] is True
    assert step["apply_commands"] == [["/tmp/materialize", "--json"]]
    assert "plugin-cache-materialize" in plan["recommended_order"]


def test_apply_repair_plan_runs_only_auto_apply_steps(monkeypatch) -> None:
    monkeypatch.setattr(
        remediation,
        "build_registry",
        lambda: {
            "status": "warn",
            "summary": {"components": {"plugin_drift": "warn"}},
            "findings": [
                {
                    "component": "plugin_drift",
                    "id": "plugin_cache_needs_materialization",
                    "severity": "warn",
                    "materialize_command": ["materialize", "--json"],
                }
            ],
            "components": {},
        },
    )
    runs: list[list[str]] = []

    def fake_run(command, **kwargs):
        runs.append(command)
        class Result:
            returncode = 0
            stdout = "ok"
            stderr = ""

        return Result()

    monkeypatch.setattr(remediation.subprocess, "run", fake_run)

    report = apply_repair_plan(verify=False)
    assert report["status"] == "ok"
    assert runs == [["materialize", "--json"]]
