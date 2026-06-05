"""Local telegram-kit install: skill symlink + tg CLI on PATH."""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from .paths import CONTROL_ROOT, LIVE_SKILL, MCP_REPO, PLUGIN_PACKAGE


@dataclass(frozen=True)
class KitInstallResult:
    status: str
    dry_run: bool
    actions: list[dict[str, str]]
    errors: list[str]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _home_bin() -> Path:
    return Path.home() / "bin"


def _skill_target() -> Path:
    return PLUGIN_PACKAGE / "skills" / "telegram"


def _materialize_host_adapters(*, dry_run: bool) -> list[dict[str, str]]:
    actions: list[dict[str, str]] = []
    adapter_script = MCP_REPO / "bin/install-adapters"
    if not adapter_script.is_file():
        return actions
    output_dir = CONTROL_ROOT / "generated/adapters"
    if not dry_run:
        import subprocess

        subprocess.run(
            [
                str(adapter_script),
                "--host",
                "all",
                "--apply",
                "--output-dir",
                str(output_dir),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
    actions.append(
        {
            "action": "adapters",
            "path": str(output_dir),
            "target": "codex,claude,opencode,cursor,standalone routing snippets",
        }
    )
    return actions


def plan_local_install(*, dry_run: bool) -> KitInstallResult:
    actions: list[dict[str, str]] = []
    errors: list[str] = []

    skill_target = _skill_target()
    if not skill_target.is_dir():
        errors.append(f"missing skill source: {skill_target}")
    else:
        actions.append(
            {
                "action": "symlink",
                "path": str(LIVE_SKILL),
                "target": str(skill_target),
            }
        )

    tg_source = MCP_REPO / "bin" / "tg"
    tg_dest = _home_bin() / "tg"
    tg_wrapper = CONTROL_ROOT / "bin/tg"
    if not tg_wrapper.is_file():
        errors.append(f"missing tg CLI wrapper: {tg_wrapper}")
    else:
        actions.append(
            {
                "action": "symlink",
                "path": str(tg_dest),
                "target": str(tg_wrapper),
            }
        )

    routing_note = (
        "Codex live read: tg read today <chat> --limit 30 --json first. "
        "Do not use mcporter/tool_search/README/doctor before read. "
        "Fallback: telegram-fast-read-today → telegram_read mode=fast. "
        "See tools/telegram/generated/adapters/codex/telegram-codex-entry.md"
    )
    actions.append(
        {
            "action": "note",
            "path": str(CONTROL_ROOT / "docs" / "agent-routing-note.txt"),
            "content": routing_note,
        }
    )
    actions.extend(_materialize_host_adapters(dry_run=dry_run))

    if errors:
        return KitInstallResult(status="fail", dry_run=dry_run, actions=actions, errors=errors)

    if not dry_run:
        _home_bin().mkdir(parents=True, exist_ok=True)
        if skill_target.is_dir():
            LIVE_SKILL.parent.mkdir(parents=True, exist_ok=True)
            if LIVE_SKILL.exists() or LIVE_SKILL.is_symlink():
                LIVE_SKILL.unlink()
            LIVE_SKILL.symlink_to(skill_target)
        if tg_wrapper.is_file():
            if tg_dest.exists() or tg_dest.is_symlink():
                tg_dest.unlink()
            tg_dest.symlink_to(tg_wrapper)
        if tg_source.is_file():
            os.chmod(tg_source, 0o755)
        note_path = CONTROL_ROOT / "docs" / "agent-routing-note.txt"
        note_path.parent.mkdir(parents=True, exist_ok=True)
        note_path.write_text(routing_note + "\n", encoding="utf-8")

    return KitInstallResult(status="ok", dry_run=dry_run, actions=actions, errors=[])


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Install local Telegram kit (skill + tg)")
    parser.add_argument("command", nargs="?", default="install", choices=["install"])
    parser.add_argument("--local", action="store_true", help="Install for this Mac only")
    parser.add_argument("--skill", action="store_true", help="Link ~/.agents/skills/telegram")
    parser.add_argument("--tg", action="store_true", help="Link ~/bin/tg")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    if not (args.local or args.skill or args.tg):
        args.local = True
        args.skill = True
        args.tg = True

    result = plan_local_install(dry_run=args.dry_run)
    if args.json:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(f"status: {result.status}")
        for item in result.actions:
            print(f"- {item.get('action')}: {item.get('path')}")
        for err in result.errors:
            print(f"error: {err}", file=sys.stderr)
    return 0 if result.status == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())