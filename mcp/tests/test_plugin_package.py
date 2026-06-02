import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from telegram_mcp.plugin_package import build_plugin_package, find_package_hygiene_issues


class PluginPackageTests(unittest.TestCase):
    def _make_plugin_source(self, root: Path) -> Path:
        source = root / "source"
        (source / ".codex-plugin").mkdir(parents=True)
        (source / "skills" / "telegram").mkdir(parents=True)
        (source / "assets").mkdir(parents=True)
        (source / ".codex-plugin" / "plugin.json").write_text(
            json.dumps({"name": "telegram", "version": "0.1.7"}),
            encoding="utf-8",
        )
        (source / ".mcp.json").write_text('{"mcpServers": {}}\n', encoding="utf-8")
        (source / ".app.json").write_text('{"apps": {}}\n', encoding="utf-8")
        (source / "README.md").write_text("# Telegram\n", encoding="utf-8")
        (source / "skills" / "telegram" / "SKILL.md").write_text("# Telegram skill\n", encoding="utf-8")
        (source / "assets" / "telegram-small.png").write_bytes(b"png")
        return source

    def test_build_plugin_package_copies_to_plain_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self._make_plugin_source(root)
            output = root / "release" / "telegram-plugin"

            result = build_plugin_package(source_dir=source, output_dir=output)

            self.assertEqual(result.status, "ok")
            self.assertEqual(result.file_count, 6)
            self.assertTrue((output / ".codex-plugin" / "plugin.json").exists())
            self.assertTrue((output / "skills" / "telegram" / "SKILL.md").exists())
            self.assertFalse(output.is_symlink())

    def test_hygiene_blocks_private_paths_and_runtime_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self._make_plugin_source(root)
            (source / ".env").write_text("secret=1\n", encoding="utf-8")
            (source / ".DS_Store").write_bytes(b"finder")
            (source / "skills" / "telegram" / "SKILL.md").write_text(
                "source: /Users/sereja/private\n",
                encoding="utf-8",
            )

            issues = find_package_hygiene_issues(source)

            self.assertIn(".env: forbidden runtime artifact", issues)
            self.assertIn(".DS_Store: forbidden runtime artifact", issues)
            self.assertIn("skills/telegram/SKILL.md: hardcoded private path", issues)

    def test_bin_wrapper_builds_package(self):
        repo_root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self._make_plugin_source(root)
            output = root / "package"

            result = subprocess.run(
                [
                    str(repo_root / "bin" / "build-plugin-package"),
                    "--source-dir",
                    str(source),
                    "--output-dir",
                    str(output),
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
            self.assertTrue((output / "README.md").exists())
