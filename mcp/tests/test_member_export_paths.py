import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from telegram_mcp.member_export_paths import resolve_member_export_dir


class MemberExportPathTests(unittest.TestCase):
    def test_explicit_output_dir_inside_git_tree_is_allowed(self) -> None:
        with self.subTest("git tree"):
            with TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root / ".git").mkdir()
                output_dir = root / "exports"

                resolved = resolve_member_export_dir(str(output_dir))

                self.assertEqual(resolved, output_dir.resolve(strict=False))
                self.assertTrue(output_dir.is_dir())


if __name__ == "__main__":
    unittest.main()
