import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from telegram_mcp import runtime
from telegram_mcp.config import get_settings


def _run(awaitable):
    return asyncio.run(awaitable)


class RuntimeConfigTests(unittest.TestCase):
    def setUp(self):
        get_settings.cache_clear()

    def tearDown(self):
        get_settings.cache_clear()

    def test_read_port_defaults_to_project_http_port(self):
        env = {k: v for k, v in __import__("os").environ.items() if k != "TELEGRAM_MCP_PORT"}
        with patch.dict("os.environ", env, clear=True):
            get_settings.cache_clear()
            self.assertEqual(runtime.read_port(), 8799)

    def test_read_port_uses_env_override(self):
        with patch.dict("os.environ", {"TELEGRAM_MCP_PORT": "9001"}, clear=False):
            get_settings.cache_clear()
            self.assertEqual(runtime.read_port(), 9001)

    def test_run_server_applies_http_defaults_for_streamable_http(self):
        with patch.dict(
            "os.environ",
            {
                "TELEGRAM_MCP_TRANSPORT": "streamable-http",
                "TELEGRAM_MCP_HOST": "127.0.0.1",
                "TELEGRAM_MCP_PORT": "8799",
                "TELEGRAM_MCP_HTTP_PATH": "/mcp",
                "TELEGRAM_MCP_MOUNT_PATH": "/",
                "TELEGRAM_MCP_AUTH_TOKEN": "test-token",
            },
            clear=False,
        ):
            get_settings.cache_clear()
            with patch.object(runtime.mcp, "run") as mcp_run:
                runtime.run_server()

        self.assertEqual(runtime.mcp.settings.host, "127.0.0.1")
        self.assertEqual(runtime.mcp.settings.port, 8799)
        self.assertEqual(runtime.mcp.settings.streamable_http_path, "/mcp")
        self.assertEqual(runtime.mcp.settings.mount_path, "/")
        self.assertTrue(runtime.mcp.settings.json_response)
        mcp_run.assert_called_once_with(transport="streamable-http")

    def test_run_server_allows_disabling_json_response(self):
        with patch.dict(
            "os.environ",
            {
                "TELEGRAM_MCP_TRANSPORT": "streamable-http",
                "TELEGRAM_MCP_JSON_RESPONSE": "false",
                "TELEGRAM_MCP_AUTH_TOKEN": "test-token",
            },
            clear=False,
        ):
            get_settings.cache_clear()
            with patch.object(runtime.mcp, "run") as mcp_run:
                runtime.run_server()

        self.assertFalse(runtime.mcp.settings.json_response)
        mcp_run.assert_called_once_with(transport="streamable-http")

    def test_configure_transport_auth_replaces_oauth_metadata_route(self):
        original_routes = list(runtime.mcp._custom_starlette_routes)
        try:
            with patch.dict(
                "os.environ",
                {
                    "TELEGRAM_MCP_TRANSPORT": "streamable-http",
                    "TELEGRAM_MCP_HOST": "127.0.0.1",
                    "TELEGRAM_MCP_PORT": "8799",
                    "TELEGRAM_MCP_AUTH_TOKEN": "test-token",
                },
                clear=False,
            ):
                get_settings.cache_clear()
                runtime.configure_transport_auth("streamable-http")
                runtime.configure_transport_auth("streamable-http")

            routes = [
                route
                for route in runtime.mcp._custom_starlette_routes
                if getattr(route, "path", None)
                == runtime.OAUTH_AUTHORIZATION_SERVER_METADATA_PATH
            ]
            self.assertEqual(len(routes), 1)
        finally:
            runtime.mcp._custom_starlette_routes = original_routes

    def test_run_server_disconnects_shared_wrapper_on_shutdown(self):
        with patch("telegram_mcp.runtime.shared_mode_enabled", return_value=True):
            with patch.object(runtime.mcp, "run") as mcp_run:
                with patch(
                    "telegram_mcp.runtime._disconnect_shared_wrapper",
                    AsyncMock(),
                ) as disconnect_wrapper:
                    runtime.run_server()

        mcp_run.assert_called_once()
        disconnect_wrapper.assert_awaited_once()

    def test_shared_wrapper_connect_failure_is_not_cached(self):
        class FlakyWrapper:
            attempts = 0

            def __init__(self, _settings):
                self.connected = False

            async def connect(self):
                type(self).attempts += 1
                if type(self).attempts == 1:
                    raise TimeoutError("connect timeout")
                self.connected = True

        runtime._shared_wrapper = None
        try:
            with patch("telegram_mcp.runtime.get_settings", return_value=object()):
                with patch("telegram_mcp.runtime.TelegramWrapper", FlakyWrapper):
                    with self.assertRaises(TimeoutError):
                        _run(runtime.get_or_connect_shared_wrapper())

                    self.assertIsNone(runtime._shared_wrapper)
                    wrapper = _run(runtime.get_or_connect_shared_wrapper())

            self.assertTrue(wrapper.connected)
            self.assertIs(runtime._shared_wrapper, wrapper)
            self.assertEqual(FlakyWrapper.attempts, 2)
        finally:
            runtime._shared_wrapper = None

    def test_shared_wrapper_prewarm_uses_read_path_without_get_me(self):
        wrapper = type(
            "Wrapper",
            (),
            {
                "get_me": AsyncMock(side_effect=AssertionError("get_me prewarm disabled")),
                "read_today_dialog": AsyncMock(return_value=object()),
            },
        )()

        _run(runtime._prewarm_shared_wrapper(wrapper))

        wrapper.get_me.assert_not_awaited()
        wrapper.read_today_dialog.assert_awaited_once()

    def test_read_transport_rejects_invalid_value(self):
        with patch.dict(
            "os.environ",
            {"TELEGRAM_MCP_TRANSPORT": "http"},
            clear=False,
        ):
            get_settings.cache_clear()
            with self.assertRaisesRegex(ValueError, "Invalid TELEGRAM_MCP_TRANSPORT"):
                runtime.read_transport()

    def test_get_runtime_report_for_stdio(self):
        with patch.dict(
            "os.environ",
            {"TELEGRAM_MCP_TRANSPORT": "stdio"},
            clear=False,
        ):
            get_settings.cache_clear()
            report = runtime.get_runtime_report()

        self.assertEqual(report["transport"], "stdio")
        self.assertIsNone(report["endpoint_url"])
        self.assertIsNone(report["port"])

    def test_get_runtime_report_for_http_transport(self):
        with patch.dict(
            "os.environ",
            {
                "TELEGRAM_MCP_TRANSPORT": "streamable-http",
                "TELEGRAM_MCP_HOST": "0.0.0.0",
                "TELEGRAM_MCP_PORT": "9000",
                "TELEGRAM_MCP_HTTP_PATH": "/telegram",
            },
            clear=False,
        ):
            get_settings.cache_clear()
            report = runtime.get_runtime_report()

        self.assertEqual(report["transport"], "streamable-http")
        self.assertEqual(report["port"], 9000)
        self.assertEqual(report["endpoint_url"], "http://0.0.0.0:9000/telegram")
