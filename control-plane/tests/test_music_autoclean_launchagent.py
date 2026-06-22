from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "install_telegram_music_autoclean_launchagent.sh"


def test_music_autoclean_launchagent_installer_dry_run_is_non_mutating(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    runtime = tmp_path / "runtime"
    env = os.environ.copy() | {"HOME": str(home)}

    proc = subprocess.run(
        [str(SCRIPT), "--runtime-root", str(runtime), "--dry-run"],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["ok"] is True
    assert payload["mode"] == "dry_run"
    assert payload["label"] == "com.sereja.telegram-music-autoclean"
    assert payload["runtime_root"] == str(runtime.resolve())
    assert not (home / "Library" / "LaunchAgents").exists()


def test_music_autoclean_launchagent_installer_requires_live_gate(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    runtime = tmp_path / "runtime"
    env = os.environ.copy() | {"HOME": str(home)}
    env.pop("TELEGRAM_MUSIC_AUTOCLEAN_ALLOW_LIVE", None)

    proc = subprocess.run(
        [str(SCRIPT), "--runtime-root", str(runtime)],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert proc.returncode == 2
    assert "live launchd installation is disabled" in proc.stderr
    assert not (home / "Library" / "LaunchAgents").exists()


def test_music_autoclean_launchagent_installer_rejects_runtime_inside_project() -> None:
    proc = subprocess.run(
        [str(SCRIPT), "--runtime-root", str(ROOT / "runtime"), "--dry-run"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert proc.returncode != 0
    assert "runtime root must not live inside project root" in proc.stderr
