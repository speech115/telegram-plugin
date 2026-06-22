import json
import tempfile
import unittest
from pathlib import Path

from telegram_mcp.plugin_materialize import materialize_plugin_cache


class PluginMaterializeTests(unittest.TestCase):
    def _write_minimal_plugin(self, root: Path, *, version: str = "9.9.9") -> None:
        manifest_dir = root / ".codex-plugin"
        manifest_dir.mkdir(parents=True, exist_ok=True)
        (manifest_dir / "plugin.json").write_text(
            json.dumps({"name": "telegram", "version": version}),
            encoding="utf-8",
        )
        skill = root / "skills" / "telegram"
        skill.mkdir(parents=True, exist_ok=True)
        (skill / "SKILL.md").write_text("telegram skill\n", encoding="utf-8")
        (root / ".mcp.json").write_text('{"mcpServers": {}}\n', encoding="utf-8")

    def test_materialize_copies_versioned_cache_tree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            cache_root = root / "cache"
            self._write_minimal_plugin(source, version="1.2.3")

            result = materialize_plugin_cache(source_dir=source, cache_root=cache_root)
            self.assertEqual(result.status, "ok")
            self.assertEqual(result.version, "1.2.3")
            target = cache_root / "1.2.3" / "skills" / "telegram" / "SKILL.md"
            self.assertTrue(target.exists())
            self.assertEqual(target.read_text(encoding="utf-8"), "telegram skill\n")


if __name__ == "__main__":
    unittest.main()