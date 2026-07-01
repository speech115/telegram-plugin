import importlib.util
import unittest

from telegram_mcp.tdlib_download import assert_isolated_from_telethon, should_route_to_tdlib

PYTDBOT_AVAILABLE = importlib.util.find_spec("pytdbot") is not None


class ShouldRouteToTdlibTests(unittest.TestCase):
    def test_routes_when_all_conditions_met(self):
        self.assertTrue(
            should_route_to_tdlib(
                account="main",
                tdlib_enabled=True,
                content_kind="video",
                media_size_bytes=30 * 1024 * 1024,
                threshold_mb=20,
            )
        )

    def test_rejects_non_main_account(self):
        self.assertFalse(
            should_route_to_tdlib(
                account="pl",
                tdlib_enabled=True,
                content_kind="video",
                media_size_bytes=30 * 1024 * 1024,
                threshold_mb=20,
            )
        )

    def test_rejects_when_disabled(self):
        self.assertFalse(
            should_route_to_tdlib(
                account="main",
                tdlib_enabled=False,
                content_kind="video",
                media_size_bytes=30 * 1024 * 1024,
                threshold_mb=20,
            )
        )

    def test_rejects_unsupported_content_kind(self):
        self.assertFalse(
            should_route_to_tdlib(
                account="main",
                tdlib_enabled=True,
                content_kind=None,
                media_size_bytes=30 * 1024 * 1024,
                threshold_mb=20,
            )
        )

    def test_rejects_below_threshold(self):
        self.assertFalse(
            should_route_to_tdlib(
                account="main",
                tdlib_enabled=True,
                content_kind="video",
                media_size_bytes=1 * 1024 * 1024,
                threshold_mb=20,
            )
        )

    def test_rejects_unknown_size(self):
        self.assertFalse(
            should_route_to_tdlib(
                account="main",
                tdlib_enabled=True,
                content_kind="video",
                media_size_bytes=None,
                threshold_mb=20,
            )
        )


class AssertIsolatedFromTelethonTests(unittest.TestCase):
    def test_rejects_telethon_session_tree(self):
        with self.assertRaises(ValueError):
            assert_isolated_from_telethon("/Users/x/.telegram-mcp/main")

    def test_accepts_isolated_directory(self):
        assert_isolated_from_telethon("/Users/x/.telegram-mcp-tdlib/main")


@unittest.skipUnless(PYTDBOT_AVAILABLE, "pytdbot not installed (optional [tdlib] extra)")
class PytdbotDependentTests(unittest.TestCase):
    def test_raise_if_error_passes_through_non_error_result(self):
        from telegram_mcp.tdlib_download import raise_if_error

        self.assertEqual(raise_if_error("some value"), "some value")

    def test_raise_if_error_raises_on_pytdbot_error(self):
        import pytdbot

        from telegram_mcp.tdlib_download import raise_if_error

        error = pytdbot.types.Error(code=400, message="MESSAGE_ID_INVALID")
        with self.assertRaisesRegex(RuntimeError, "MESSAGE_ID_INVALID"):
            raise_if_error(error)

    def test_extract_file_id_from_message_video(self):
        import pytdbot

        from telegram_mcp.tdlib_download import extract_file_id_from_message

        message = pytdbot.types.Message(
            content=pytdbot.types.MessageVideo(
                video=pytdbot.types.Video(video=pytdbot.types.File(id=555, size=52_428_800))
            )
        )
        self.assertEqual(extract_file_id_from_message(message), 555)

    def test_extract_file_id_from_message_unsupported_type(self):
        import pytdbot

        from telegram_mcp.tdlib_download import extract_file_id_from_message

        message = pytdbot.types.Message(content=pytdbot.types.MessageText())
        with self.assertRaisesRegex(ValueError, "unsupported message content type"):
            extract_file_id_from_message(message)

    def test_build_client_rejects_telethon_session_tree(self):
        from telegram_mcp.tdlib_download import build_client

        with self.assertRaises(ValueError):
            build_client(
                api_id=1,
                api_hash="hash",
                files_directory="/Users/x/.telegram-mcp/main",
            )


if __name__ == "__main__":
    unittest.main()
