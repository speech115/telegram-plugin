import json
import tempfile
import unittest
from pathlib import Path

from telegram_mcp.agent_doc_sync import (
    build_agent_docs,
    check_agent_docs_sync,
    sync_agent_docs,
    transform_routing,
)


class AgentDocSyncTests(unittest.TestCase):
    def _make_plugin(self, root: Path) -> Path:
        plugin = root / "plugin"
        skill = plugin / "skills" / "telegram"
        (skill / "agent-docs" / "static").mkdir(parents=True)
        (skill / "references").mkdir(parents=True)
        (skill / "references" / "facade-routing.md").write_text(
            "# Facade Routing\n\n- On the local Sereja host, use `telegram-fast-read-today`.\n",
            encoding="utf-8",
        )
        (skill / "references" / "source-evidence-broker.md").write_text(
            "# Source Evidence Broker\n\n- `live_mcp`: current.\n",
            encoding="utf-8",
        )
        (skill / "references" / "media-and-voice.md").write_text(
            "# Media And Voice\n\n## Media Inspection\n\n- Download files.\n",
            encoding="utf-8",
        )
        (skill / "agent-docs" / "static" / "writes.md").write_text("# Write safety\n", encoding="utf-8")
        (skill / "agent-docs" / "manifest.json").write_text(
            json.dumps(
                {
                    "version": 1,
                    "topics": {
                        "routing": {
                            "from_reference": "references/facade-routing.md",
                            "transform": "routing",
                        },
                        "sources": {
                            "from_reference": "references/source-evidence-broker.md",
                            "transform": "sources",
                        },
                        "media": {
                            "from_reference": "references/media-and-voice.md",
                            "transform": "media",
                        },
                        "tools": {"transform": "tools_from_facade"},
                        "writes": {"static": "static/writes.md"},
                        "index": {"transform": "index"},
                    },
                }
            ),
            encoding="utf-8",
        )
        return plugin

    def test_transform_routing_removes_private_host_paths(self):
        text = transform_routing(
            "# Facade Routing\n\n- On the local Sereja host, use shortcut.\n"
        )

        self.assertNotIn("/Users/sereja", text)
        self.assertNotIn("Sereja", text)
        self.assertIn("local read-only adapter", text)

    def test_sync_writes_mcp_docs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plugin = self._make_plugin(root)
            mcp_repo = root / "telegram-mcp"
            (mcp_repo / "docs").mkdir(parents=True)

            result = sync_agent_docs(plugin, mcp_repo_dir=mcp_repo)

            self.assertEqual(result.status, "ok")
            self.assertTrue((mcp_repo / "docs" / "agent" / "routing.md").exists())
            self.assertTrue((plugin / "skills" / "telegram" / "agent-docs" / "tools.md").exists())

    def test_check_detects_stale_docs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plugin = self._make_plugin(root)
            mcp_repo = root / "telegram-mcp"
            (mcp_repo / "docs" / "agent").mkdir(parents=True)
            (mcp_repo / "docs" / "agent" / "routing.md").write_text("stale\n", encoding="utf-8")

            result = check_agent_docs_sync(plugin, mcp_repo_dir=mcp_repo)

            self.assertEqual(result.status, "drift")
            self.assertTrue(any(item.startswith("stale:") for item in result.drift))

    def test_build_includes_tools_from_facade_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            plugin = self._make_plugin(Path(tmp))
            docs = build_agent_docs(plugin)

            self.assertIn("telegram_read", docs["tools"])
            self.assertIn("## Not on default surface", docs["tools"])
            self.assertIn("`send_dialog_message`", docs["tools"])