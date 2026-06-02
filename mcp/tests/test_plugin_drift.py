import contextlib
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from telegram_mcp.plugin_drift import check_plugin_drift, main


class PluginDriftTests(unittest.TestCase):
    def _write_enabled_config(self, root: Path) -> Path:
        config = root / "config.toml"
        config.write_text(
            (
                '[plugins."telegram@sereja-local"]\n'
                "enabled = true\n\n"
                "[marketplaces.sereja-local]\n"
                f'source = "{root.as_posix()}"\n'
            ),
            encoding="utf-8",
        )
        return config

    def _write_marketplace(self, root: Path) -> Path:
        marketplace = root / ".agents" / "plugins" / "marketplace.json"
        marketplace.parent.mkdir(parents=True)
        marketplace.write_text(
            json.dumps(
                {
                    "name": "sereja-local",
                    "plugins": [
                        {
                            "name": "telegram",
                            "source": {"source": "local", "path": "./plugins/telegram"},
                            "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
                            "category": "Productivity",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        return marketplace

    def test_reports_ok_for_matching_skill_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            live = root / "live" / "SKILL.md"
            marketplace = root / "marketplace" / "SKILL.md"
            cache = root / "cache" / "SKILL.md"
            live.parent.mkdir(parents=True)
            marketplace.parent.mkdir(parents=True)
            cache.parent.mkdir(parents=True)
            live.write_text("same skill\n", encoding="utf-8")
            marketplace.write_text("same skill\n", encoding="utf-8")
            cache.write_text("same skill\n", encoding="utf-8")

            report = check_plugin_drift(
                live_skill_path=live,
                plugin_source_skill_path=live,
                marketplace_skill_path=marketplace,
                plugin_cache_skill_path=cache,
                plugin_source_mcp_path=root / "missing" / ".mcp.json",
                codex_config_path=root / "missing" / "config.toml",
                local_marketplace_path=root / "missing" / "marketplace.json",
            )

            self.assertEqual(report.status, "ok")
            self.assertEqual(report.canonical_source, "plugin_source_skill")
            self.assertTrue(report.sync_safe)
            self.assertEqual(report.live_skill.sha256, report.plugin_cache_skill.sha256)

    def test_resolves_local_marketplace_source_and_installer_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            live = root / "live" / "SKILL.md"
            source = root / "source" / "SKILL.md"
            cache = root / "cache" / "SKILL.md"
            source_mcp = root / "source" / ".mcp.json"
            for path in (live, source, cache, source_mcp):
                path.parent.mkdir(parents=True, exist_ok=True)
            live.write_text("same skill\n", encoding="utf-8")
            source.write_text("same skill\n", encoding="utf-8")
            cache.write_text("same skill\n", encoding="utf-8")
            source_mcp.write_text('{"mcpServers": {}}\n', encoding="utf-8")
            config = self._write_enabled_config(root)
            marketplace = self._write_marketplace(root)

            report = check_plugin_drift(
                live_skill_path=live,
                plugin_source_skill_path=source,
                marketplace_skill_path=cache,
                plugin_cache_skill_path=cache,
                plugin_source_mcp_path=source_mcp,
                codex_config_path=config,
                local_marketplace_path=marketplace,
            )

            self.assertEqual(
                report.installer_flow.command,
                [
                    "codex",
                    "plugin",
                    "remove",
                    "telegram@sereja-local",
                    "&&",
                    "codex",
                    "plugin",
                    "add",
                    "telegram@sereja-local",
                ],
            )
            self.assertEqual(report.installer_flow.source_path, str((root / "plugins" / "telegram").resolve()))
            self.assertTrue(report.codex_plugin_config.enabled)
            self.assertTrue(report.local_marketplace.plugin_declared)
            self.assertTrue(report.installer_flow.safe_to_apply)

    def test_reports_installer_ready_when_source_matches_live_but_cache_lags(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            live = root / "live" / "SKILL.md"
            source = root / "source" / "SKILL.md"
            marketplace = root / "marketplace" / "SKILL.md"
            cache = root / "cache" / "SKILL.md"
            source_mcp = root / "source" / ".mcp.json"
            for path in (live, source, marketplace, cache, source_mcp):
                path.parent.mkdir(parents=True, exist_ok=True)
            live.write_text("new facade\n", encoding="utf-8")
            source.write_text("new facade\n", encoding="utf-8")
            marketplace.write_text("old facade\n", encoding="utf-8")
            cache.write_text("old facade\n", encoding="utf-8")
            source_mcp.write_text('{"mcpServers": {}}\n', encoding="utf-8")
            config = self._write_enabled_config(root)
            marketplace_json = self._write_marketplace(root)

            report = check_plugin_drift(
                live_skill_path=live,
                plugin_source_skill_path=source,
                marketplace_skill_path=marketplace,
                plugin_cache_skill_path=cache,
                plugin_source_mcp_path=source_mcp,
                codex_config_path=config,
                local_marketplace_path=marketplace_json,
            )

            self.assertEqual(report.status, "installer_ready_drift")
            self.assertEqual(report.canonical_source, "plugin_source_skill")
            self.assertTrue(report.sync_safe)
            self.assertTrue(report.installer_flow.safe_to_apply)
            self.assertIn("installer flow", report.recommendation)

    def test_auto_cache_path_uses_source_manifest_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plugin_root = root / "plugins" / "telegram"
            live = root / "live" / "SKILL.md"
            source = plugin_root / "skills" / "telegram" / "SKILL.md"
            cache = root / "cache" / "telegram" / "0.2.0" / "skills" / "telegram" / "SKILL.md"
            manifest = plugin_root / ".codex-plugin" / "plugin.json"
            cache_manifest = root / "cache" / "telegram" / "0.2.0" / ".codex-plugin" / "plugin.json"
            source_mcp = plugin_root / ".mcp.json"
            cache_mcp = root / "cache" / "telegram" / "0.2.0" / ".mcp.json"
            for path in (live, source, cache, manifest, cache_manifest, source_mcp, cache_mcp):
                path.parent.mkdir(parents=True, exist_ok=True)
            live.write_text("same skill\n", encoding="utf-8")
            source.write_text("same skill\n", encoding="utf-8")
            cache.write_text("same skill\n", encoding="utf-8")
            manifest.write_text('{"name":"telegram","version":"0.2.0"}\n', encoding="utf-8")
            cache_manifest.write_text('{"name":"telegram","version":"0.2.0"}\n', encoding="utf-8")
            source_mcp.write_text('{"mcpServers": {}}\n', encoding="utf-8")
            cache_mcp.write_text('{"mcpServers": {}}\n', encoding="utf-8")
            config = self._write_enabled_config(root)
            marketplace = self._write_marketplace(root)

            report = check_plugin_drift(
                live_skill_path=live,
                plugin_source_skill_path=source,
                plugin_cache_root=root / "cache" / "telegram",
                plugin_source_mcp_path=source_mcp,
                codex_config_path=config,
                local_marketplace_path=marketplace,
            )

            self.assertEqual(report.status, "ok")
            self.assertEqual(report.plugin_source_manifest.version, "0.2.0")
            self.assertIn("/0.2.0/", report.plugin_cache_skill.path)

    def test_reports_metadata_drift_when_mcp_files_differ(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            live = root / "live" / "SKILL.md"
            source = root / "source" / "SKILL.md"
            marketplace = root / "marketplace" / "SKILL.md"
            cache = root / "cache" / "SKILL.md"
            source_mcp = root / "source" / ".mcp.json"
            cache_mcp = root / "cache" / ".mcp.json"
            for path in (live, source, marketplace, cache, source_mcp, cache_mcp):
                path.parent.mkdir(parents=True, exist_ok=True)
            live.write_text("same skill\n", encoding="utf-8")
            source.write_text("same skill\n", encoding="utf-8")
            marketplace.write_text("same skill\n", encoding="utf-8")
            cache.write_text("same skill\n", encoding="utf-8")
            source_mcp.write_text('{"mcpServers":{"telegram-local":{"allowedTools":["get_me"]}}}\n', encoding="utf-8")
            cache_mcp.write_text('{"mcpServers":{"telegram-local":{"allowedTools":["get_me","old_tool"]}}}\n', encoding="utf-8")

            report = check_plugin_drift(
                live_skill_path=live,
                plugin_source_skill_path=source,
                marketplace_skill_path=marketplace,
                plugin_cache_skill_path=cache,
                plugin_source_mcp_path=source_mcp,
                plugin_cache_mcp_path=cache_mcp,
            )

            self.assertEqual(report.status, "metadata_drift")
            self.assertEqual(report.canonical_source, "plugin_source_skill")
            self.assertTrue(report.sync_safe)

    def test_reports_installer_ready_when_reference_file_lags_but_skill_md_matches(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plugin_root = root / "plugins" / "telegram"
            live_root = root / "live-skill"
            source_root = plugin_root / "skills" / "telegram"
            marketplace_root = root / "marketplace" / "skills" / "telegram"
            cache_root = root / "cache" / "telegram" / "0.2.0" / "skills" / "telegram"
            manifest = plugin_root / ".codex-plugin" / "plugin.json"
            source_mcp = plugin_root / ".mcp.json"
            cache_mcp = root / "cache" / "telegram" / "0.2.0" / ".mcp.json"
            for skill_root in (live_root, source_root, marketplace_root, cache_root):
                (skill_root / "references").mkdir(parents=True, exist_ok=True)
                (skill_root / "scripts").mkdir(parents=True, exist_ok=True)
                (skill_root / "SKILL.md").write_text("same skill\n", encoding="utf-8")
                (skill_root / "references/facade-routing.md").write_text("new routing\n", encoding="utf-8")
                (skill_root / "scripts/helper.py").write_text("print('same')\n", encoding="utf-8")
            (marketplace_root / "references/facade-routing.md").write_text("old routing\n", encoding="utf-8")
            (cache_root / "references/facade-routing.md").write_text("old routing\n", encoding="utf-8")
            manifest.parent.mkdir(parents=True, exist_ok=True)
            manifest.write_text('{"name":"telegram","version":"0.2.0"}\n', encoding="utf-8")
            source_mcp.write_text('{"mcpServers": {}}\n', encoding="utf-8")
            cache_mcp.write_text('{"mcpServers": {}}\n', encoding="utf-8")
            config = self._write_enabled_config(root)
            marketplace = self._write_marketplace(root)

            report = check_plugin_drift(
                live_skill_path=live_root / "SKILL.md",
                plugin_source_skill_path=source_root / "SKILL.md",
                marketplace_skill_path=marketplace_root / "SKILL.md",
                plugin_cache_root=root / "cache" / "telegram",
                plugin_source_mcp_path=source_mcp,
                codex_config_path=config,
                local_marketplace_path=marketplace,
            )

            self.assertEqual(report.status, "installer_ready_drift")
            self.assertEqual(report.canonical_source, "plugin_source_skill")
            self.assertTrue(report.sync_safe)
            self.assertEqual(report.live_skill.sha256, report.plugin_cache_skill.sha256)
            self.assertNotEqual(report.plugin_source_skill_tree.sha256, report.plugin_cache_skill_tree.sha256)
            self.assertIn("plugin_source_vs_cache_skill_tree", report.tree_diff)
            self.assertIn(
                "references/facade-routing.md",
                report.tree_diff["plugin_source_vs_cache_skill_tree"]["changed"],
            )

    def test_reports_drift_for_different_skill_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            live = root / "live" / "SKILL.md"
            cache = root / "cache" / "SKILL.md"
            live.parent.mkdir(parents=True)
            cache.parent.mkdir(parents=True)
            live.write_text("new facade\n", encoding="utf-8")
            cache.write_text("old facade\n", encoding="utf-8")

            report = check_plugin_drift(
                live_skill_path=live,
                plugin_source_skill_path=live,
                marketplace_skill_path=root / "missing" / "SKILL.md",
                plugin_cache_skill_path=cache,
                plugin_source_mcp_path=root / "missing" / ".mcp.json",
                codex_config_path=root / "missing" / "config.toml",
                local_marketplace_path=root / "missing" / "marketplace.json",
            )

            self.assertEqual(report.status, "installer_ready_drift")
            self.assertEqual(report.canonical_source, "plugin_source_skill")
            self.assertTrue(report.sync_safe)
            self.assertFalse(report.installer_flow.safe_to_apply)
            self.assertNotEqual(report.live_skill.sha256, report.plugin_cache_skill.sha256)

    def test_reports_source_drift_when_cache_only_matches_marketplace_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            live = root / "live" / "SKILL.md"
            source = root / "source" / "SKILL.md"
            marketplace = root / "marketplace" / "SKILL.md"
            cache = root / "cache" / "SKILL.md"
            source_mcp = root / "source" / ".mcp.json"
            cache_mcp = root / "cache" / ".mcp.json"
            for path in (live, source, marketplace, cache, source_mcp, cache_mcp):
                path.parent.mkdir(parents=True, exist_ok=True)
            live.write_text("new live facade\n", encoding="utf-8")
            source.write_text("old source facade\n", encoding="utf-8")
            marketplace.write_text("installed facade\n", encoding="utf-8")
            cache.write_text("installed facade\n", encoding="utf-8")
            source_mcp.write_text('{"mcpServers": {}}\n', encoding="utf-8")
            cache_mcp.write_text('{"mcpServers": {}}\n', encoding="utf-8")

            report = check_plugin_drift(
                live_skill_path=live,
                plugin_source_skill_path=source,
                marketplace_skill_path=marketplace,
                plugin_cache_skill_path=cache,
                plugin_source_mcp_path=source_mcp,
                plugin_cache_mcp_path=cache_mcp,
            )

            self.assertEqual(report.status, "source_drift")
            self.assertEqual(report.canonical_source, "unproven")
            self.assertFalse(report.sync_safe)
            self.assertEqual(
                report.source_candidates,
                ["live_skill", "plugin_source_skill", "marketplace_skill", "plugin_cache_skill"],
            )
            self.assertTrue(report.plugin_source_mcp.valid_json)
            self.assertTrue(report.plugin_cache_mcp.valid_json)

    def test_strict_mode_fails_on_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            live = root / "live" / "SKILL.md"
            cache = root / "cache" / "SKILL.md"
            live.parent.mkdir(parents=True)
            cache.parent.mkdir(parents=True)
            live.write_text("new facade\n", encoding="utf-8")
            cache.write_text("old facade\n", encoding="utf-8")

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(
                    [
                        "--live-skill",
                        str(live),
                        "--plugin-source-skill",
                        str(live),
                        "--marketplace-skill",
                        str(cache),
                        "--plugin-cache-skill",
                        str(cache),
                        "--strict",
                        "--json",
                    ]
                )

            self.assertEqual(exit_code, 1)

    def test_bin_wrapper_reports_json(self):
        repo_root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            live = root / "live" / "SKILL.md"
            cache = root / "cache" / "SKILL.md"
            live.parent.mkdir(parents=True)
            cache.parent.mkdir(parents=True)
            live.write_text("same skill\n", encoding="utf-8")
            cache.write_text("same skill\n", encoding="utf-8")

            result = subprocess.run(
                [
                    str(repo_root / "bin" / "check-plugin-drift"),
                    "--live-skill",
                    str(live),
                    "--plugin-source-skill",
                    str(live),
                    "--marketplace-skill",
                    str(cache),
                    "--plugin-cache-skill",
                    str(cache),
                    "--json",
                ],
                cwd=repo_root,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["status"], "ok")
            self.assertEqual(payload["canonical_source"], "plugin_source_skill")
            self.assertTrue(payload["sync_safe"])
            self.assertIn("plugin_source_skill_tree", payload)
            self.assertIn("plugin_cache_skill_tree", payload)
