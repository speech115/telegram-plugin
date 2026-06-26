import unittest
from unittest.mock import patch
from pathlib import Path
from tempfile import TemporaryDirectory

from telegram_mcp.member_export_paths import resolve_member_export_dir


class MemberExportPathTests(unittest.TestCase):
    def test_explicit_output_dir_inside_private_export_root_is_allowed(self) -> None:
        with TemporaryDirectory() as tmp:
            home = Path(tmp)
            output_dir = home / ".cache" / "telegram-mcp" / "member-exports" / "job-1"

            with patch.dict("os.environ", {"HOME": str(home)}):
                resolved = resolve_member_export_dir(str(output_dir))

            self.assertEqual(resolved, output_dir.resolve(strict=False))
            self.assertTrue(output_dir.is_dir())

    def test_explicit_output_dir_outside_private_export_root_is_rejected(self) -> None:
        with TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            outside = Path(tmp) / "exports"

            with patch.dict("os.environ", {"HOME": str(home)}):
                with self.assertRaisesRegex(ValueError, "private export root"):
                    resolve_member_export_dir(str(outside))


if __name__ == "__main__":
    unittest.main()
