import json
import os
import shutil
import stat
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
BIN_DIR = REPO_ROOT / "bin"


class OpsScriptsTests(unittest.TestCase):
    def _write_executable(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)

    def _make_fake_project(
        self,
        *,
        health_exit: int = 0,
        doctor_exit: int = 0,
        unittest_exit: int = 0,
        compileall_exit: int = 0,
        mcporter_call_exit: int = 0,
        mcporter_list_exit: int = 0,
        mcporter_facade_exit: int = 0,
        transport: str = "streamable-http",
        include_python: bool = True,
        include_mcporter: bool = False,
    ) -> Path:
        root = Path(tempfile.mkdtemp(prefix="telegram-mcp-ops-"))
        (root / "scripts").mkdir(parents=True, exist_ok=True)
        (root / "bin").mkdir(parents=True, exist_ok=True)
        shutil.copy2(SCRIPTS_DIR / "status.sh", root / "scripts" / "status.sh")
        shutil.copy2(
            SCRIPTS_DIR / "smoke-check.sh",
            root / "scripts" / "smoke-check.sh",
        )
        shutil.copy2(
            SCRIPTS_DIR / "install-launchd.sh",
            root / "scripts" / "install-launchd.sh",
        )
        shutil.copy2(SCRIPTS_DIR / "check.sh", root / "scripts" / "check.sh")
        shutil.copy2(BIN_DIR / "status", root / "bin" / "status")
        shutil.copy2(BIN_DIR / "doctor", root / "bin" / "doctor")

        python_stub = textwrap.dedent(
            f"""\
            #!/bin/sh
            printf '%s\\n' "$*" >> "${{HOME}}/.python-invocations"
            if [ "${{1:-}}" = "-m" ] && [ "${{2:-}}" = "unittest" ]; then
              exit {unittest_exit}
            fi
            if [ "${{1:-}}" = "-m" ] && [ "${{2:-}}" = "compileall" ]; then
              exit {compileall_exit}
            fi
            for last; do :; done
            mode="${{last:-}}"
            runtime_transport="${{TELEGRAM_MCP_TRANSPORT:-{transport}}}"
            if [ "${{TELEGRAM_TEST_STDERR_NOISE:-0}}" = "1" ]; then
              echo "stderr noise from mcp/httpx" >&2
            fi
            if [ "$mode" = "health" ]; then
              attempts_file="${{HOME}}/.python-health-invocations"
              printf 'health\\n' >> "$attempts_file"
              fail_before_ready="${{TELEGRAM_TEST_HEALTH_FAILS_BEFORE_READY:-0}}"
              if [ "$fail_before_ready" -gt 0 ]; then
                count="$(wc -l < "$attempts_file" | tr -d ' ')"
                if [ "$count" -le "$fail_before_ready" ]; then
                  echo "{{\\"connected\\": false, \\"authorized\\": false, \\"transport\\": \\"$runtime_transport\\"}}"
                  exit 1
                fi
              fi
              echo "{{\\"connected\\": false, \\"authorized\\": false, \\"transport\\": \\"$runtime_transport\\"}}"
              exit {health_exit}
            fi
            if [ "$mode" = "doctor" ]; then
              echo "{{\\"status\\": \\"ok\\", \\"transport\\": \\"$runtime_transport\\"}}"
              exit {doctor_exit}
            fi
            echo "unexpected args: $*" >&2
            exit 64
            """
        )
        if include_python:
            self._write_executable(root / ".venv" / "bin" / "python", python_stub)

        if include_mcporter:
            mcporter_stub = textwrap.dedent(
                f"""\
                #!/bin/sh
                if [ "$1" = "call" ] && [ "$2" = "telegram.resolve_dialog" ]; then
                  echo '{{"id":123,"dialog_ref":"tg://dialog/user/123","name":"Smoke Chat","type":"user","resolved_from":"me","match_confidence":1.0}}'
                  exit 0
                fi
                if [ "$1" = "call" ] && [ "$2" = "telegram.collect_dialog_context" ]; then
                  echo '{{"chat":{{"dialog_ref":"tg://dialog/user/123","id":123,"name":"Smoke Chat","type":"user","username":"smokechat","resolved_from":"123","match_confidence":1.0}},"messages":[],"message_count":0,"collection_mode":"fast","has_more_before":false,"next_offset_id":null,"range":{{"date_from":null,"date_to":null}},"data_source":"live_telegram"}}'
                  exit {mcporter_facade_exit}
                fi
                if [ "$1" = "call" ]; then
                  echo '{{"id": 1, "first_name": "Test"}}'
                  exit {mcporter_call_exit}
                fi
                if [ "$1" = "list" ]; then
                  echo '{{"status": "ok"}}'
                  exit {mcporter_list_exit}
                fi
                echo "unexpected args: $*" >&2
                exit 64
                """
            )
            self._write_executable(
                root / "fake-bin" / "mcporter",
                mcporter_stub,
            )

        self._write_executable(
            root / "fake-bin" / "launchctl",
            textwrap.dedent(
                """\
                #!/bin/sh
                state_file="${HOME}/.launchctl-http-loaded"
                rotate_state_file="${HOME}/.launchctl-logrotate-loaded"
                printf '%s\n' "$*" >> "${HOME}/.launchctl-invocations"

                case "$1" in
                  bootout)
                    if [ "${LAUNCHCTL_SIMULATE_STALE_SERVICE:-0}" = "1" ]; then
                      if [ "$2" = "gui/$(id -u)/com.sereja.telegram-mcp-http" ]; then
                        echo "Could not find service \"$2\" in domain for user gui: $(id -u)" >&2
                        exit 113
                      fi
                      if [ "$2" = "gui/$(id -u)" ] && [ "${3:-}" = "${HOME}/Library/LaunchAgents/com.sereja.telegram-mcp-http.plist" ]; then
                        rm -f "$state_file"
                        exit 0
                      fi
                    fi

                    if [ "$2" = "gui/$(id -u)" ] && [ "${3:-}" = "${HOME}/Library/LaunchAgents/com.sereja.telegram-mcp-http.plist" ]; then
                      rm -f "$state_file"
                      exit 0
                    fi
                    if [ "$2" = "gui/$(id -u)" ] && [ "${3:-}" = "${HOME}/Library/LaunchAgents/com.sereja.telegram-mcp-http-logrotate.plist" ]; then
                      rm -f "$rotate_state_file"
                      exit 0
                    fi
                    exit 0
                    ;;
                  bootstrap)
                    if [ "$2" = "gui/$(id -u)" ] && [ "$3" = "${HOME}/Library/LaunchAgents/com.sereja.telegram-mcp-http.plist" ]; then
                      if [ -f "$state_file" ]; then
                        echo "Bootstrap failed: 5: Input/output error" >&2
                        exit 5
                      fi
                      : > "$state_file"
                      exit 0
                    fi
                    if [ "$2" = "gui/$(id -u)" ] && [ "$3" = "${HOME}/Library/LaunchAgents/com.sereja.telegram-mcp-http-logrotate.plist" ]; then
                      : > "$rotate_state_file"
                      exit 0
                    fi
                    exit 0
                    ;;
                  kickstart)
                    exit 0
                    ;;
                esac

                echo "launchctl stub: unexpected args: $*" >&2
                exit 64
                """
            ),
        )
        self._write_executable(
            root / "fake-bin" / "nc",
            "#!/bin/sh\necho 'nc stub'\nexit 0\n",
        )
        return root

    def _run_script(self, root: Path, script_name: str, **env_overrides: str):
        env = os.environ.copy()
        env.update(
            {
                "HOME": str(root),
                "PATH": f"{root / 'fake-bin'}:{env.get('PATH', '')}",
                "TELEGRAM_MCP_AUTH_TOKEN": "test-token",
            }
        )
        env.update(env_overrides)
        return subprocess.run(
            ["bash", str(root / "scripts" / script_name)],
            cwd=root,
            text=True,
            capture_output=True,
            env=env,
        )

    def _run_bin(self, root: Path, bin_name: str, *args: str, **env_overrides: str):
        env = os.environ.copy()
        env.update(
            {
                "HOME": str(root),
                "PATH": f"{root / 'fake-bin'}:{env.get('PATH', '')}",
                "TELEGRAM_MCP_AUTH_TOKEN": "test-token",
            }
        )
        env.update(env_overrides)
        return subprocess.run(
            ["bash", str(root / "bin" / bin_name), *args],
            cwd=root,
            text=True,
            capture_output=True,
            env=env,
        )

    def test_status_script_reports_health_and_doctor_exit_codes(self):
        root = self._make_fake_project(
            health_exit=1,
            doctor_exit=2,
            transport="stdio",
        )

        result = self._run_script(
            root,
            "status.sh",
            TELEGRAM_MCP_TRANSPORT="stdio",
        )

        self.assertEqual(result.returncode, 0)
        self.assertIn("health exit code: 1", result.stdout)
        self.assertIn("doctor exit code: 2", result.stdout)

    def test_bin_status_defaults_to_daemon_transport_and_parses_stdout_only(self):
        root = self._make_fake_project()

        result = self._run_bin(
            root,
            "status",
            "--json",
            TELEGRAM_TEST_STDERR_NOISE="1",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["health"]["transport"], "streamable-http")
        self.assertEqual(payload["doctor"]["transport"], "streamable-http")
        self.assertIn("stderr noise", payload["health_stderr"])
        self.assertIn("stderr noise", payload["doctor_stderr"])
        self.assertNotIn("health_output", payload)
        self.assertNotIn("doctor_output", payload)

    def test_bin_doctor_defaults_to_daemon_transport_and_parses_stdout_only(self):
        root = self._make_fake_project()

        result = self._run_bin(
            root,
            "doctor",
            "--json",
            TELEGRAM_TEST_STDERR_NOISE="1",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["doctor"]["transport"], "streamable-http")
        self.assertIn("stderr noise", payload["doctor_stderr"])
        self.assertNotIn("doctor_output", payload)

    def test_smoke_check_reports_health_failure_before_exit(self):
        root = self._make_fake_project(health_exit=1, doctor_exit=0)

        result = self._run_script(root, "smoke-check.sh", TELEGRAM_MCP_TRANSPORT="stdio")

        self.assertEqual(result.returncode, 1)
        self.assertIn("Health check failed with exit code 1.", result.stderr)

    def test_smoke_check_reports_doctor_failure_before_exit(self):
        root = self._make_fake_project(health_exit=0, doctor_exit=1)

        result = self._run_script(root, "smoke-check.sh", TELEGRAM_MCP_TRANSPORT="stdio")

        self.assertEqual(result.returncode, 1)
        self.assertIn("Doctor check failed with exit code 1.", result.stderr)

    def test_status_script_reports_bootstrap_hint_when_python_is_missing(self):
        root = self._make_fake_project(
            include_python=False,
            transport="stdio",
        )

        result = self._run_script(
            root,
            "status.sh",
            TELEGRAM_MCP_TRANSPORT="stdio",
        )

        self.assertEqual(result.returncode, 0)
        self.assertIn("Missing repo-local python", result.stdout)
        self.assertIn("uv pip install -e .", result.stdout)

    def test_smoke_check_reports_bootstrap_hint_when_python_is_missing(self):
        root = self._make_fake_project(
            include_python=False,
            transport="stdio",
        )

        result = self._run_script(
            root,
            "smoke-check.sh",
            TELEGRAM_MCP_TRANSPORT="stdio",
        )

        self.assertEqual(result.returncode, 1)
        self.assertIn("Missing repo-local python", result.stderr)
        self.assertIn("uv pip install -e .", result.stderr)

    def test_status_script_uses_mcporter_for_daemon_checks(self):
        root = self._make_fake_project(
            include_python=False,
            include_mcporter=True,
        )

        result = self._run_script(root, "status.sh")

        self.assertEqual(result.returncode, 0)
        self.assertIn('"probe": "mcporter call telegram.get_me"', result.stdout)
        self.assertIn('"tool_catalog": "ok"', result.stdout)
        self.assertIn("health exit code: 0", result.stdout)
        self.assertIn("doctor exit code: 0", result.stdout)

    def test_smoke_check_uses_mcporter_for_daemon_checks(self):
        root = self._make_fake_project(
            include_python=False,
            include_mcporter=True,
        )

        result = self._run_script(root, "smoke-check.sh")

        self.assertEqual(result.returncode, 0)
        self.assertIn("Running telegram-mcp daemon health via mcporter...", result.stdout)
        self.assertIn("Running telegram-mcp daemon doctor via mcporter...", result.stdout)
        self.assertIn("Smoke check passed.", result.stdout)

    def test_smoke_check_runs_facade_probe_for_daemon_checks(self):
        root = self._make_fake_project(
            include_python=False,
            include_mcporter=True,
        )

        result = self._run_script(root, "smoke-check.sh")

        self.assertEqual(result.returncode, 0)
        self.assertIn("Running telegram-mcp daemon facade smoke via mcporter...", result.stdout)
        self.assertIn("Facade smoke dialog ref: tg://dialog/user/123", result.stdout)
        self.assertIn("Smoke check passed.", result.stdout)

    def test_smoke_check_reports_facade_probe_failure_in_daemon_mode(self):
        root = self._make_fake_project(
            include_python=False,
            include_mcporter=True,
            mcporter_facade_exit=1,
        )

        result = self._run_script(root, "smoke-check.sh")

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "Facade smoke check failed: mcporter call telegram.collect_dialog_context returned non-zero.",
            result.stderr,
        )

    def test_status_script_reports_mcporter_hint_when_missing_in_daemon_mode(self):
        root = self._make_fake_project(include_python=False)

        result = self._run_script(
            root,
            "status.sh",
            PATH=f"{root / 'fake-bin'}:/bin:/usr/bin",
        )

        self.assertEqual(result.returncode, 0)
        self.assertIn("Missing mcporter in PATH", result.stdout)

    def test_smoke_check_reports_mcporter_hint_when_missing_in_daemon_mode(self):
        root = self._make_fake_project(include_python=False)

        result = self._run_script(
            root,
            "smoke-check.sh",
            PATH=f"{root / 'fake-bin'}:/bin:/usr/bin",
        )

        self.assertEqual(result.returncode, 1)
        self.assertIn("Missing mcporter in PATH", result.stderr)

    def test_install_launchd_reports_missing_python_before_bootstrap(self):
        root = self._make_fake_project(include_python=False)

        result = self._run_script(
            root,
            "install-launchd.sh",
            TELEGRAM_API_ID="1",
            TELEGRAM_API_HASH="hash",
        )

        self.assertEqual(result.returncode, 1)
        self.assertIn("Missing repo-local python", result.stderr)
        self.assertIn("uv pip install -e .", result.stderr)

    def test_install_launchd_writes_optional_diagnostics_env_vars(self):
        root = self._make_fake_project(include_python=True)

        result = self._run_script(
            root,
            "install-launchd.sh",
            TELEGRAM_API_ID="1",
            TELEGRAM_API_HASH="hash",
            TELEGRAM_MCP_INCLUDE_DIAGNOSTICS="true",
            TELEGRAM_CACHE_TTL="15",
            TELEGRAM_RESULT_CACHE_SIZE="64",
        )

        self.assertEqual(result.returncode, 0)
        plist_path = root / "Library" / "LaunchAgents" / "com.sereja.telegram-mcp-http.plist"
        plist = plist_path.read_text(encoding="utf-8")
        self.assertIn("<key>TELEGRAM_MCP_INCLUDE_DIAGNOSTICS</key>", plist)
        self.assertIn("<string>true</string>", plist)
        self.assertIn("<key>TELEGRAM_CACHE_TTL</key>", plist)
        self.assertIn("<string>15</string>", plist)
        self.assertIn("<key>TELEGRAM_RESULT_CACHE_SIZE</key>", plist)
        self.assertIn("<string>64</string>", plist)

    def test_install_launchd_boots_out_existing_service_by_plist_path(self):
        root = self._make_fake_project(include_python=True)
        (root / ".launchctl-http-loaded").write_text("loaded", encoding="utf-8")

        result = self._run_script(
            root,
            "install-launchd.sh",
            TELEGRAM_API_ID="1",
            TELEGRAM_API_HASH="hash",
            LAUNCHCTL_SIMULATE_STALE_SERVICE="1",
        )

        self.assertEqual(result.returncode, 0)
        self.assertIn("Installed and restarted", result.stdout)

    def test_install_launchd_does_not_kickstart_long_running_daemon(self):
        root = self._make_fake_project(include_python=True)

        result = self._run_script(
            root,
            "install-launchd.sh",
            TELEGRAM_API_ID="1",
            TELEGRAM_API_HASH="hash",
        )

        self.assertEqual(result.returncode, 0)
        invocations = (root / ".launchctl-invocations").read_text(encoding="utf-8")
        self.assertNotIn("kickstart -k gui/", invocations)

    def test_install_launchd_waits_for_daemon_readiness(self):
        root = self._make_fake_project(include_python=True)

        result = self._run_script(
            root,
            "install-launchd.sh",
            TELEGRAM_API_ID="1",
            TELEGRAM_API_HASH="hash",
            TELEGRAM_TEST_HEALTH_FAILS_BEFORE_READY="2",
            TELEGRAM_MCP_READY_ATTEMPTS="3",
            TELEGRAM_MCP_READY_INTERVAL="0",
        )

        self.assertEqual(result.returncode, 0)
        self.assertIn("Waiting for daemon readiness via health probe", result.stdout)
        self.assertIn("Daemon health probe ready on attempt 3", result.stdout)
        attempts = (root / ".python-health-invocations").read_text(encoding="utf-8")
        self.assertEqual(attempts.count("health"), 3)

    def test_install_launchd_fails_when_daemon_never_becomes_ready(self):
        root = self._make_fake_project(include_python=True, health_exit=1)

        result = self._run_script(
            root,
            "install-launchd.sh",
            TELEGRAM_API_ID="1",
            TELEGRAM_API_HASH="hash",
            TELEGRAM_MCP_READY_ATTEMPTS="2",
            TELEGRAM_MCP_READY_INTERVAL="0",
        )

        self.assertEqual(result.returncode, 1)
        self.assertIn("Daemon did not become ready after 2 attempts.", result.stderr)
        self.assertIn("./scripts/status.sh", result.stderr)

    def test_check_script_runs_unittest_compileall_and_smoke(self):
        root = self._make_fake_project(include_python=True, include_mcporter=True)

        result = self._run_script(root, "check.sh")

        self.assertEqual(result.returncode, 0)
        self.assertIn("Running unit tests", result.stdout)
        self.assertIn("Running bytecode compilation", result.stdout)
        self.assertIn("Running smoke check", result.stdout)
        self.assertIn("All checks passed.", result.stdout)
        invocations = (root / ".python-invocations").read_text(encoding="utf-8")
        self.assertIn("-m unittest discover -s tests -p test_*.py", invocations)
        self.assertIn("-m compileall src tests", invocations)

    def test_check_script_fails_when_unittest_fails(self):
        root = self._make_fake_project(include_python=True, unittest_exit=1)

        result = self._run_script(root, "check.sh")

        self.assertEqual(result.returncode, 1)
        self.assertIn("Running unit tests", result.stdout)
