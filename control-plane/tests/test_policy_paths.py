import os
import unittest
from pathlib import Path
from unittest import mock

from telegram_control_plane.policy_paths import resolve_policy_path


class PolicyPathTests(unittest.TestCase):
    def test_expands_env_with_default(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            path = resolve_policy_path("${TELEGRAM_MCP_REPO:-./mcp}")
        self.assertEqual(path, Path("./mcp"))

    def test_prefers_env_over_default(self) -> None:
        with mock.patch.dict(os.environ, {"TELEGRAM_MCP_REPO": "/tmp/mcp"}, clear=True):
            path = resolve_policy_path("${TELEGRAM_MCP_REPO:-./mcp}")
        self.assertEqual(path, Path("/tmp/mcp"))

    def test_plain_path_expands_user(self) -> None:
        path = resolve_policy_path("~/plugin")
        self.assertEqual(path, Path.home() / "plugin")