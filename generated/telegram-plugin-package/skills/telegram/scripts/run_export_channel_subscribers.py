#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
PLUGIN_EXPORTER = SCRIPT_DIR / "export_channel_subscribers.py"
LIVE_SKILL_DIR = Path(
    os.environ.get(
        "TELEGRAM_LIVE_SKILL_DIR",
        str(Path.home() / ".agents" / "skills" / "telegram"),
    )
)
LIVE_EXPORTER = LIVE_SKILL_DIR / "scripts" / "export_channel_subscribers.py"


def choose_exporter() -> Path:
    prefer_live = os.environ.get("TELEGRAM_SUBSCRIBER_EXPORTER_SOURCE") == "live"
    candidates = [LIVE_EXPORTER, PLUGIN_EXPORTER] if prefer_live else [PLUGIN_EXPORTER, LIVE_EXPORTER]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise SystemExit(
        "Missing subscriber exporter. Checked: "
        + ", ".join(str(candidate) for candidate in candidates)
    )


def main() -> None:
    exporter = choose_exporter()
    os.execv(sys.executable, [sys.executable, str(exporter), *sys.argv[1:]])


if __name__ == "__main__":
    main()
