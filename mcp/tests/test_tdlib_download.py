import importlib.util
import unittest

from telegram_mcp.tdlib_download import (
    TdlibDownloadError,
    assert_isolated_from_telethon,
    should_route_to_tdlib,
    start_client_ready,
)

PYTDBOT_AVAILABLE = importlib.util.find_spec("pytdbot") is not None


class _FakeClient:
    """Minimal stand-in for pytdbot.Client for start_client_ready tests.

    start_client_ready never imports pytdbot itself — it only calls
    ``start(wait_login=False)`` and reads ``authorization_state`` — so it can
    be exercised without the optional extra installed.
    """

    def __init__(self, states):
        # states: list of authorization_state values yielded on each read;
        # the last value repeats once exhausted.
        self._states = list(states)
        self.start_calls = []

    async def start(self, wait_login=True):
        self.start_calls.append(wait_login)

    @property
    def authorization_state(self):
        if len(self._states) > 1:
            return self._states.pop(0)
        return self._states[0]


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


class StartClientReadyTests(unittest.IsolatedAsyncioTestCase):
    async def test_returns_when_ready(self):
        client = _FakeClient(["authorizationStateReady"])
        await start_client_ready(client, timeout_seconds=1.0, poll_interval_seconds=0.05)
        self.assertEqual(client.start_calls, [False])  # start(wait_login=False)

    async def test_returns_once_state_becomes_ready(self):
        client = _FakeClient(
            [
                "authorizationStateWaitTdlibParameters",
                "authorizationStateWaitTdlibParameters",
                "authorizationStateReady",
            ]
        )
        await start_client_ready(client, timeout_seconds=1.0, poll_interval_seconds=0.01)

    async def test_raises_instead_of_hanging_when_unauthorized(self):
        client = _FakeClient(["authorizationStateWaitPhoneNumber"])
        with self.assertRaisesRegex(TdlibDownloadError, "not ready"):
            await start_client_ready(
                client, timeout_seconds=0.2, poll_interval_seconds=0.05
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

    def test_extract_file_id_from_message_animation(self):
        import pytdbot

        from telegram_mcp.tdlib_download import extract_file_id_from_message

        message = pytdbot.types.Message(
            content=pytdbot.types.MessageAnimation(
                animation=pytdbot.types.Animation(
                    animation=pytdbot.types.File(id=777, size=52_428_800)
                )
            )
        )
        self.assertEqual(extract_file_id_from_message(message), 777)

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
