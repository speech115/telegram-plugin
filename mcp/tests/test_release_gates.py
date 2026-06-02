import json
import tempfile
import unittest
from pathlib import Path

from telegram_mcp.release_gates import (
    audit_fresh_install_smoke,
    audit_packaging_hygiene,
    audit_prompt_safety_rules,
    run_release_gates,
)


class ReleaseGateTests(unittest.TestCase):
    def test_packaging_hygiene_flags_private_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "SKILL.md").write_text("/Users/sereja/private\n", encoding="utf-8")
            gate = audit_packaging_hygiene(root)
            self.assertEqual(gate.status, "fail")
            self.assertTrue(gate.findings)

    def test_fresh_install_smoke_passes(self) -> None:
        gate = audit_fresh_install_smoke()
        self.assertEqual(gate.status, "ok", gate.findings)

    def test_prompt_safety_rules_pass(self) -> None:
        gate = audit_prompt_safety_rules()
        self.assertEqual(gate.status, "ok", gate.findings)

    def test_run_release_gates_json_shape(self) -> None:
        report = run_release_gates()
        self.assertEqual(report["status"], "ok")
        self.assertEqual(len(report["gates"]), 2)
        json.dumps(report)