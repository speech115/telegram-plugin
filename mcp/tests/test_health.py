import json
import unittest
from contextlib import asynccontextmanager
from io import StringIO
from pathlib import Path
from unittest.mock import AsyncMock, patch

from telegram_mcp import server
from telegram_mcp.config import Settings
from telegram_mcp.locking import SessionLockError
from telegram_mcp.types import DoctorInfo, HealthInfo


def _run(awaitable):
    import asyncio

    return asyncio.run(awaitable)


class HealthTests(unittest.TestCase):
    def test_interactive_login_uses_file_session_lock(self):
        from telegram_mcp.auth import interactive_login

        events: list[str] = []
        settings = Settings(
            api_id=1,
            api_hash="hash",
            session_dir=Path("/tmp/login-session"),
            download_dir=Path("/tmp/login-downloads"),
        )

        class DummyLoginClient:
            def __init__(self, *_args, **_kwargs):
                return None

            async def start(self):
                events.append("start")

            async def get_me(self):
                return type(
                    "UserStub",
                    (),
                    {"first_name": "Sereja", "last_name": "", "username": "sereja"},
                )()

            async def disconnect(self):
                events.append("disconnect")

        class FakeLock:
            def __init__(self, _path):
                events.append("init_lock")

            def acquire(self):
                events.append("acquire_lock")

            def release(self):
                events.append("release_lock")

        with patch("telegram_mcp.auth.get_settings", return_value=settings):
            with patch("telegram_mcp.auth.TelegramClient", DummyLoginClient):
                with patch("telegram_mcp.auth.FileSessionLock", FakeLock, create=True):
                    _run(interactive_login())

        self.assertEqual(
            events,
            ["init_lock", "acquire_lock", "start", "disconnect", "release_lock"],
        )

    def test_interactive_login_surfaces_busy_session_lock(self):
        from telegram_mcp.auth import interactive_login

        settings = Settings(
            api_id=1,
            api_hash="hash",
            session_dir=Path("/tmp/login-busy-session"),
            download_dir=Path("/tmp/login-busy-downloads"),
        )

        class DummyLoginClient:
            def __init__(self, *_args, **_kwargs):
                return None

            async def start(self):
                raise AssertionError("client.start should not run when lock is busy")

        class BusyLock:
            def __init__(self, _path):
                return None

            def acquire(self):
                raise SessionLockError("busy")

        with patch("telegram_mcp.auth.get_settings", return_value=settings):
            with patch("telegram_mcp.auth.TelegramClient", DummyLoginClient):
                with patch("telegram_mcp.auth.FileSessionLock", BusyLock, create=True):
                    with self.assertRaises(SessionLockError):
                        _run(interactive_login())

    def test_get_health_report_includes_runtime_endpoint(self):
        from telegram_mcp.auth import get_health_report

        with patch("telegram_mcp.auth.get_settings") as get_settings:
            get_settings.return_value = type(
                "SettingsStub",
                (),
                {
                    "session_backend": "sqlite",
                    "download_dir": "/tmp/downloads",
                    "uses_file_session": True,
                    "session_path": "/tmp/session",
                },
            )()
            with patch(
                "telegram_mcp.auth._probe_http_runtime",
                AsyncMock(return_value=None),
            ):
                with patch(
                    "telegram_mcp.auth.get_runtime_report",
                    return_value={
                        "transport": "streamable-http",
                        "shared_client": True,
                        "host": "127.0.0.1",
                        "port": 8799,
                        "http_path": "/mcp",
                        "endpoint_url": "http://127.0.0.1:8799/mcp",
                    },
                ):
                    report = _run(get_health_report())

        self.assertEqual(report["transport"], "streamable-http")
        self.assertEqual(report["endpoint_url"], "http://127.0.0.1:8799/mcp")
        self.assertTrue(report["connected"])

    def test_get_health_report_uses_http_probe_for_daemon_transport(self):
        from telegram_mcp.auth import get_health_report

        with patch("telegram_mcp.auth.get_settings") as get_settings:
            get_settings.return_value = type(
                "SettingsStub",
                (),
                {
                    "session_backend": "sqlite",
                    "download_dir": "/tmp/downloads",
                    "uses_file_session": True,
                    "session_path": "/tmp/session",
                },
            )()
            with patch(
                "telegram_mcp.auth.get_runtime_report",
                return_value={
                    "transport": "streamable-http",
                    "shared_client": True,
                    "host": "127.0.0.1",
                    "port": 8799,
                    "http_path": "/mcp",
                    "endpoint_url": "http://127.0.0.1:8799/mcp",
                },
            ):
                with patch(
                    "telegram_mcp.auth._probe_http_runtime",
                    AsyncMock(return_value=None),
                ) as probe:
                    report = _run(get_health_report())

        probe.assert_awaited_once_with(
            "http://127.0.0.1:8799/mcp",
            transport="streamable-http",
            timeout_seconds=15.0,
        )
        self.assertTrue(report["connected"])
        self.assertTrue(report["authorized"])

    def test_get_health_report_uses_sse_probe_for_sse_transport(self):
        from telegram_mcp.auth import get_health_report

        @asynccontextmanager
        async def fake_sse_client(_url, **_kwargs):
            yield ("read-stream", "write-stream")

        session_kwargs = []

        class DummyClientSession:
            def __init__(self, read_stream, write_stream, **kwargs):
                self.read_stream = read_stream
                self.write_stream = write_stream
                self.kwargs = kwargs
                session_kwargs.append(kwargs)

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def initialize(self):
                return None

            async def call_tool(self, *_args, **_kwargs):
                return type("ToolResult", (), {"isError": False})()

        with patch("telegram_mcp.auth.get_settings") as get_settings:
            get_settings.return_value = type(
                "SettingsStub",
                (),
                {
                    "session_backend": "sqlite",
                    "download_dir": "/tmp/downloads",
                    "uses_file_session": True,
                    "session_path": "/tmp/session",
                },
            )()
            with patch(
                "telegram_mcp.auth.get_runtime_report",
                return_value={
                    "transport": "sse",
                    "shared_client": True,
                    "host": "127.0.0.1",
                    "port": 8799,
                    "http_path": "/mcp",
                    "endpoint_url": "http://127.0.0.1:8799/mcp",
                },
            ):
                with patch(
                    "mcp.client.sse.sse_client",
                    fake_sse_client,
                ) as sse_probe:
                    with patch(
                        "mcp.client.streamable_http.streamable_http_client",
                        side_effect=AssertionError("wrong transport client"),
                    ):
                        with patch(
                            "mcp.client.session.ClientSession",
                            DummyClientSession,
                        ):
                            report = _run(get_health_report())

        self.assertTrue(report["connected"])
        self.assertTrue(report["authorized"])
        self.assertIsNotNone(sse_probe)
        self.assertEqual(
            session_kwargs[0]["read_timeout_seconds"].total_seconds(),
            15.0,
        )

    def test_http_probe_sends_configured_bearer_token(self):
        from telegram_mcp.auth import _probe_http_runtime

        captured_headers = []

        @asynccontextmanager
        async def fake_streamable_http_client(_url, *, http_client, **_kwargs):
            captured_headers.append(dict(http_client.headers))
            yield ("read-stream", "write-stream", lambda: None)

        class DummyClientSession:
            def __init__(self, read_stream, write_stream, **kwargs):
                self.read_stream = read_stream
                self.write_stream = write_stream
                self.kwargs = kwargs

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def initialize(self):
                return None

            async def call_tool(self, *_args, **_kwargs):
                return type("ToolResult", (), {"isError": False})()

        with patch("telegram_mcp.auth.get_settings") as get_settings:
            get_settings.return_value = type(
                "SettingsStub",
                (),
                {"mcp_auth_token": "probe-token"},
            )()
            with patch(
                "mcp.client.streamable_http.streamable_http_client",
                fake_streamable_http_client,
            ):
                with patch(
                    "mcp.client.session.ClientSession",
                    DummyClientSession,
                ):
                    _run(
                        _probe_http_runtime(
                            "http://127.0.0.1:8799/mcp",
                            transport="streamable-http",
                        )
                    )

        self.assertEqual(captured_headers[0]["authorization"], "Bearer probe-token")

    def test_get_doctor_report_uses_http_probe_for_daemon_transport(self):
        from telegram_mcp.auth import get_doctor_report

        with patch("telegram_mcp.auth.get_settings") as get_settings:
            get_settings.return_value = type(
                "SettingsStub",
                (),
                {
                    "session_backend": "sqlite",
                    "download_dir": "/tmp/downloads",
                    "uses_file_session": True,
                    "session_dir": type(
                        "SessionDirStub",
                        (),
                        {"exists": staticmethod(lambda: True)},
                    )(),
                    "session_path": "/tmp/session",
                    "ensure_dirs": staticmethod(lambda: None),
                },
            )()
            with patch(
                "telegram_mcp.auth.get_runtime_report",
                return_value={
                    "transport": "streamable-http",
                    "shared_client": True,
                    "host": "127.0.0.1",
                    "port": 8799,
                    "http_path": "/mcp",
                    "endpoint_url": "http://127.0.0.1:8799/mcp",
                },
            ):
                with patch(
                    "telegram_mcp.auth._probe_http_runtime",
                    AsyncMock(return_value=None),
                ) as probe:
                    report = _run(get_doctor_report())

        probe.assert_awaited_once_with(
            "http://127.0.0.1:8799/mcp",
            transport="streamable-http",
            timeout_seconds=15.0,
            include_doctor=True,
        )
        self.assertEqual(report["status"], "ok")
        self.assertEqual(report["checks"]["session_lock"], "daemon-managed")
        self.assertEqual(report["checks"]["tool_call"], "ok")
        self.assertEqual(report["checks"]["scheduler"], "configured")
        self.assertEqual(report["scheduler"]["write"]["limit"], 1)

    def test_get_doctor_report_uses_live_daemon_scheduler_when_available(self):
        from telegram_mcp.auth import get_doctor_report

        live_scheduler = {"read": {"active": 2, "queued": 1, "limit": 4}}

        with patch("telegram_mcp.auth.get_settings") as get_settings:
            get_settings.return_value = type(
                "SettingsStub",
                (),
                {
                    "session_backend": "sqlite",
                    "download_dir": "/tmp/downloads",
                    "uses_file_session": True,
                    "session_dir": type(
                        "SessionDirStub",
                        (),
                        {"exists": staticmethod(lambda: True)},
                    )(),
                    "session_path": "/tmp/session",
                    "ensure_dirs": staticmethod(lambda: None),
                },
            )()
            with patch(
                "telegram_mcp.auth.get_runtime_report",
                return_value={
                    "transport": "streamable-http",
                    "shared_client": True,
                    "host": "127.0.0.1",
                    "port": 8799,
                    "http_path": "/mcp",
                    "endpoint_url": "http://127.0.0.1:8799/mcp",
                },
            ):
                with patch(
                    "telegram_mcp.auth._probe_http_runtime",
                    AsyncMock(return_value={"scheduler": live_scheduler}),
                ):
                    report = _run(get_doctor_report())

        self.assertEqual(report["checks"]["scheduler"], "live")
        self.assertEqual(report["scheduler"], live_scheduler)

    def test_get_doctor_report_uses_sse_probe_for_sse_transport(self):
        from telegram_mcp.auth import get_doctor_report

        @asynccontextmanager
        async def fake_sse_client(_url, **_kwargs):
            yield ("read-stream", "write-stream")

        session_kwargs = []

        class DummyClientSession:
            def __init__(self, read_stream, write_stream, **kwargs):
                self.read_stream = read_stream
                self.write_stream = write_stream
                self.kwargs = kwargs
                session_kwargs.append(kwargs)

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def initialize(self):
                return None

            async def call_tool(self, *_args, **_kwargs):
                return type("ToolResult", (), {"isError": False})()

        with patch("telegram_mcp.auth.get_settings") as get_settings:
            get_settings.return_value = type(
                "SettingsStub",
                (),
                {
                    "session_backend": "sqlite",
                    "download_dir": "/tmp/downloads",
                    "uses_file_session": True,
                    "session_dir": type(
                        "SessionDirStub",
                        (),
                        {"exists": staticmethod(lambda: True)},
                    )(),
                    "session_path": "/tmp/session",
                    "ensure_dirs": staticmethod(lambda: None),
                },
            )()
            with patch(
                "telegram_mcp.auth.get_runtime_report",
                return_value={
                    "transport": "sse",
                    "shared_client": True,
                    "host": "127.0.0.1",
                    "port": 8799,
                    "http_path": "/mcp",
                    "endpoint_url": "http://127.0.0.1:8799/mcp",
                },
            ):
                with patch("mcp.client.sse.sse_client", fake_sse_client):
                    with patch(
                        "mcp.client.streamable_http.streamable_http_client",
                        side_effect=AssertionError("wrong transport client"),
                    ):
                        with patch(
                            "mcp.client.session.ClientSession",
                            DummyClientSession,
                        ):
                            report = _run(get_doctor_report())

        self.assertEqual(report["status"], "ok")
        self.assertEqual(report["checks"]["tool_call"], "ok")
        self.assertEqual(
            session_kwargs[0]["read_timeout_seconds"].total_seconds(),
            15.0,
        )

    def test_health_check_returns_structured_health_info(self):
        wrapper = AsyncMock()
        wrapper.health_check.return_value = HealthInfo(
            connected=True,
            authorized=True,
            session_backend="string",
            shared_client=True,
            entity_cache_size=3,
            download_dir="/tmp/downloads",
            session_path=None,
        )

        with patch("telegram_mcp.runtime.get_tg", AsyncMock(return_value=wrapper)):
            with patch("telegram_mcp.runtime.shared_mode_enabled", return_value=True):
                result = _run(server.health_check())

        self.assertIsInstance(result, HealthInfo)
        self.assertTrue(result.connected)
        self.assertEqual(result.session_backend, "string")

    def test_main_dispatches_health_command(self):
        from telegram_mcp import __main__

        with patch("telegram_mcp.__main__.run_health") as run_health:
            with patch("sys.argv", ["telegram-mcp", "health"]):
                __main__.main()

        run_health.assert_called_once_with()

    def test_main_dispatches_doctor_command(self):
        from telegram_mcp import __main__

        with patch("telegram_mcp.__main__.run_doctor") as run_doctor:
            with patch("sys.argv", ["telegram-mcp", "doctor"]):
                __main__.main()

        run_doctor.assert_called_once_with()

    def test_run_health_prints_json(self):
        from telegram_mcp.auth import run_health

        output = StringIO()
        with patch("sys.stdout", output):
            with patch("telegram_mcp.auth.get_health_report") as get_health_report:
                get_health_report.return_value = {
                    "connected": True,
                    "authorized": True,
                    "session_backend": "sqlite",
                }
                run_health()

        data = json.loads(output.getvalue())
        self.assertTrue(data["connected"])

    def test_run_health_exits_nonzero_when_report_is_unhealthy(self):
        from telegram_mcp.auth import run_health

        output = StringIO()
        with patch("sys.stdout", output):
            with patch("telegram_mcp.auth.get_health_report") as get_health_report:
                get_health_report.return_value = {
                    "connected": False,
                    "authorized": False,
                    "session_backend": "sqlite",
                    "error": "RuntimeError: auth missing",
                }
                with self.assertRaises(SystemExit) as exc:
                    run_health()

        self.assertEqual(exc.exception.code, 1)
        data = json.loads(output.getvalue())
        self.assertFalse(data["connected"])
        self.assertFalse(data["authorized"])

    def test_doctor_tool_returns_structured_info(self):
        wrapper = AsyncMock()
        wrapper.doctor_check.return_value = DoctorInfo(
            status="ok",
            transport="streamable-http",
            session_backend="sqlite",
            checks={"session_lock": "ok", "download_dir": "ok"},
            warnings=[],
        )

        with patch("telegram_mcp.runtime.get_tg", AsyncMock(return_value=wrapper)):
            result = _run(server.doctor_check())

        self.assertIsInstance(result, DoctorInfo)
        self.assertEqual(result.checks["session_lock"], "ok")

    def test_run_doctor_prints_json(self):
        from telegram_mcp.auth import run_doctor

        output = StringIO()
        with patch("sys.stdout", output):
            with patch("telegram_mcp.auth.get_doctor_report") as get_doctor_report:
                get_doctor_report.return_value = {
                    "status": "ok",
                    "transport": "stdio",
                    "session_backend": "sqlite",
                    "checks": {"session_lock": "ok"},
                    "warnings": [],
                }
                run_doctor()

        data = json.loads(output.getvalue())
        self.assertEqual(data["status"], "ok")

    def test_run_doctor_exits_nonzero_when_status_is_not_ok(self):
        from telegram_mcp.auth import run_doctor

        output = StringIO()
        with patch("sys.stdout", output):
            with patch("telegram_mcp.auth.get_doctor_report") as get_doctor_report:
                get_doctor_report.return_value = {
                    "status": "warn",
                    "transport": "stdio",
                    "session_backend": "sqlite",
                    "checks": {"session_lock": "busy"},
                    "warnings": ["lock busy"],
                }
                with self.assertRaises(SystemExit) as exc:
                    run_doctor()

        self.assertEqual(exc.exception.code, 1)
        data = json.loads(output.getvalue())
        self.assertEqual(data["status"], "warn")
