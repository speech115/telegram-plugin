from contextlib import suppress
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from telegram_mcp import server


class ServerLifespanTests(IsolatedAsyncioTestCase):
    async def test_lifespan_does_not_disconnect_when_connect_fails(self):
        events = []

        class FailingWrapper:
            def __init__(self, _settings):
                return None

            async def connect(self):
                events.append("connect")
                raise RuntimeError("boom")

            async def disconnect(self):
                events.append("disconnect")

        with patch("telegram_mcp.runtime.shared_mode_enabled", return_value=False):
            with patch("telegram_mcp.runtime.TelegramWrapper", FailingWrapper):
                with patch("telegram_mcp.runtime.get_settings", return_value=object()):
                    with suppress(RuntimeError):
                        async with server.lifespan(server.mcp):
                            pass

        self.assertEqual(events, ["connect"])

    async def test_shared_lifespan_keeps_global_wrapper_alive(self):
        wrapper = object()

        with patch("telegram_mcp.runtime.shared_mode_enabled", return_value=True):
            with patch(
                "telegram_mcp.runtime.get_or_connect_shared_wrapper",
                AsyncMock(return_value=wrapper),
            ) as get_wrapper:
                with patch(
                    "telegram_mcp.runtime._disconnect_shared_wrapper",
                    AsyncMock(),
                ) as disconnect_wrapper:
                    with patch(
                        "telegram_mcp.runtime.get_settings",
                        return_value=SimpleNamespace(
                            telemetry_prometheus_enabled=False,
                            write_approval_required=False,
                        ),
                    ):
                        async with server.lifespan(server.mcp) as context:
                            self.assertIs(context["tg"], wrapper)

        get_wrapper.assert_awaited_once()
        disconnect_wrapper.assert_not_awaited()
