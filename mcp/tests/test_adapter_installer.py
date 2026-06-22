import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from telegram_mcp.adapter_installer import plan_adapter_install, write_plan


class AdapterInstallerTests(unittest.TestCase):
    def test_dry_run_plans_all_host_adapters_without_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            plan = plan_adapter_install(hosts=["all"], output_dir=root)

            self.assertTrue(plan.dry_run)
            self.assertEqual(plan.status, "ok")
            self.assertEqual(plan.hosts, ["codex", "claude", "opencode", "cursor", "standalone"])
            self.assertEqual(
                {item.path for item in plan.planned_files},
                {
                    "adapters/codex/telegram.mcp.json",
                    "adapters/codex/telegram-codex-entry.md",
                    "adapters/codex/telegram-routing-note.txt",
                    "adapters/claude/telegram.mcp.json",
                    "adapters/claude/telegram-routing-note.txt",
                    "adapters/opencode/opencode.json",
                    "adapters/opencode/telegram-routing-note.txt",
                    "adapters/cursor/telegram-routing.mdc",
                    "adapters/cursor/telegram-routing-note.txt",
                    "skills/telegram/INSTALL.md",
                    "adapters/standalone/telegram-routing-note.txt",
                },
            )
            self.assertEqual(list(root.iterdir()), [])

    def test_apply_writes_only_to_output_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = plan_adapter_install(hosts=["codex"], output_dir=root, dry_run=False)

            write_plan(plan)

            written = root / "adapters" / "codex" / "telegram.mcp.json"
            self.assertTrue(written.exists())
            payload = json.loads(written.read_text(encoding="utf-8"))
            self.assertEqual(payload["mcpServers"]["telegram-local"]["url"], "http://127.0.0.1:8799/mcp")
            self.assertNotIn("/Users/sereja", written.read_text(encoding="utf-8"))

    def test_bin_wrapper_reports_json_plan(self):
        repo_root = Path(__file__).resolve().parents[1]

        result = subprocess.run(
            [
                str(repo_root / "bin" / "install-adapters"),
                "--host",
                "codex",
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
        self.assertTrue(payload["dry_run"])
        self.assertEqual(payload["hosts"], ["codex"])
