"""Dry-run generator for Telegram agent host adapters."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from .facade_manifest import codex_mcp_json


DEFAULT_ENDPOINT = "http://127.0.0.1:8799/mcp"
DEFAULT_TOKEN_ENV = "TELEGRAM_MCP_AUTH_TOKEN"
HOSTS = ("codex", "claude", "opencode", "cursor", "standalone")

ROUTING_NOTE = (
    "For Telegram tasks: use the `telegram` skill. For live reads (today/recent/search), "
    "run `tg` first — do not require `@telegram`. Use direct full MCP for media, sends, and fallback. "
    "For sends with explicit target and exact text, prefer `telegram_send` / `send_message`; "
    "preview/confirmed tools are optional."
)

CODEX_ENTRY_CARD = """# Codex: Telegram live read hot path

Do not load the full telegram skill for «что нового» / read chat today.

## Run first

```bash
tg read today <chat> --limit 30 --json
```

Fallbacks (stop on first success): `telegram-fast-read-today` → MCP `telegram_read` mode=fast limit≤30.

Optional: MCP resource `telegram://docs/routing` (5 lines). Not this file on every turn.

## Forbidden before read succeeds

- mcporter / MCP server discovery
- tool_search for how to read Telegram
- plugin README, doctor_check, launchd
- @telegram bootstrap for a simple read
- mirror / telecrawl for today/latest

## After read

Reuse `chat.dialog_ref`. Sends are direct when the user gave an explicit target
and exact text: prefer `telegram_send` / `send_message`. Use preview/confirmed
tools only when the user asks to preview first.

Install tg: tools/telegram/bin/telegram-kit --local
"""


@dataclass(frozen=True)
class PlannedFile:
    path: str
    description: str
    content: str


@dataclass(frozen=True)
class AdapterInstallPlan:
    status: str
    dry_run: bool
    output_dir: str
    hosts: list[str]
    endpoint: str
    token_env: str
    planned_files: list[PlannedFile]
    warnings: list[str]
    errors: list[str]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _host_list(raw_hosts: list[str]) -> list[str]:
    if "all" in raw_hosts:
        return list(HOSTS)
    unknown = sorted(set(raw_hosts) - set(HOSTS))
    if unknown:
        raise ValueError(f"unknown hosts: {', '.join(unknown)}")
    return list(dict.fromkeys(raw_hosts))


def _json_block(payload: dict[str, object]) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def _codex_adapter(endpoint: str, token_env: str) -> PlannedFile:
    return PlannedFile(
        path="adapters/codex/telegram.mcp.json",
        description="Codex MCP server config snippet for the local Telegram facade",
        content=codex_mcp_json(endpoint=endpoint, token_env=token_env),
    )


def _claude_adapter(endpoint: str, token_env: str) -> PlannedFile:
    return PlannedFile(
        path="adapters/claude/telegram.mcp.json",
        description="Claude Code MCP server config snippet for the local Telegram facade",
        content=_json_block(
            {
                "mcpServers": {
                    "telegram": {
                        "type": "http",
                        "url": endpoint,
                        "headers": {
                            "Authorization": f"Bearer ${{{token_env}}}",
                        },
                    }
                }
            }
        ),
    )


def _opencode_adapter(endpoint: str, token_env: str) -> PlannedFile:
    return PlannedFile(
        path="adapters/opencode/opencode.json",
        description="OpenCode MCP server config snippet for the local Telegram facade",
        content=_json_block(
            {
                "mcp": {
                    "telegram": {
                        "type": "http",
                        "url": endpoint,
                        "headers": {
                            "Authorization": f"Bearer ${{{token_env}}}",
                        },
                    }
                }
            }
        ),
    )


def _routing_note_adapter(host: str) -> PlannedFile:
    return PlannedFile(
        path=f"adapters/{host}/telegram-routing-note.txt",
        description=f"Always-on Telegram routing note for {host}",
        content=ROUTING_NOTE + "\n",
    )


def _codex_entry_card_adapter() -> PlannedFile:
    return PlannedFile(
        path="adapters/codex/telegram-codex-entry.md",
        description="Codex-first Telegram read hot path (paste into AGENTS or pin in workspace)",
        content=CODEX_ENTRY_CARD,
    )


def _cursor_rules_snippet() -> PlannedFile:
    return PlannedFile(
        path="adapters/cursor/telegram-routing.mdc",
        description="Cursor rule snippet for Telegram routing (copy into .cursor/rules if desired)",
        content=(
            "---\n"
            "description: Telegram live reads via tg CLI; direct sends require explicit target/text\n"
            "globs:\n"
            "alwaysApply: true\n"
            "---\n\n"
            + ROUTING_NOTE
            + "\n"
        ),
    )


def _standalone_skill_adapter() -> PlannedFile:
    return PlannedFile(
        path="skills/telegram/INSTALL.md",
        description="Standalone skill install notes for natural-language Telegram routing",
        content=(
            "# Telegram Skill Install\n\n"
            "Install the `telegram` skill directory into the host skill root. "
            "After installation, use natural language such as `read today's Telegram chat with ...`; "
            "do not require users to invoke `@telegram`.\n"
        ),
    )


def plan_adapter_install(
    *,
    hosts: list[str],
    output_dir: str | Path,
    endpoint: str = DEFAULT_ENDPOINT,
    token_env: str = DEFAULT_TOKEN_ENV,
    dry_run: bool = True,
) -> AdapterInstallPlan:
    selected_hosts = _host_list(hosts)
    planned: list[PlannedFile] = []
    for host in selected_hosts:
        if host == "codex":
            planned.append(_codex_adapter(endpoint, token_env))
            planned.append(_codex_entry_card_adapter())
            planned.append(_routing_note_adapter("codex"))
        elif host == "claude":
            planned.append(_claude_adapter(endpoint, token_env))
            planned.append(_routing_note_adapter("claude"))
        elif host == "opencode":
            planned.append(_opencode_adapter(endpoint, token_env))
            planned.append(_routing_note_adapter("opencode"))
        elif host == "cursor":
            planned.append(_cursor_rules_snippet())
            planned.append(_routing_note_adapter("cursor"))
        elif host == "standalone":
            planned.append(_standalone_skill_adapter())
            planned.append(_routing_note_adapter("standalone"))

    warnings = [
        "dry-run artifacts are adapter snippets, not live host config writes",
        "real install still requires a running telegram-mcp daemon and a local auth token",
    ]
    return AdapterInstallPlan(
        status="ok",
        dry_run=dry_run,
        output_dir=str(Path(output_dir)),
        hosts=selected_hosts,
        endpoint=endpoint,
        token_env=token_env,
        planned_files=planned,
        warnings=warnings,
        errors=[],
    )


def write_plan(plan: AdapterInstallPlan) -> None:
    base = Path(plan.output_dir)
    for item in plan.planned_files:
        target = base / item.path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(item.content, encoding="utf-8")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate Telegram agent host adapter snippets.")
    parser.add_argument(
        "--host",
        action="append",
        choices=[*HOSTS, "all"],
        default=[],
        help="Host adapter to plan. Repeatable. Defaults to all.",
    )
    parser.add_argument("--output-dir", default="generated/adapters", help="Directory for planned/applied artifacts.")
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT, help="Local telegram-mcp HTTP endpoint.")
    parser.add_argument("--token-env", default=DEFAULT_TOKEN_ENV, help="Environment variable containing the bearer token.")
    parser.add_argument("--apply", action="store_true", help="Write adapter snippets to --output-dir.")
    parser.add_argument("--json", action="store_true", help="Print a machine-readable plan.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    hosts = args.host or ["all"]
    try:
        plan = plan_adapter_install(
            hosts=hosts,
            output_dir=args.output_dir,
            endpoint=args.endpoint,
            token_env=args.token_env,
            dry_run=not args.apply,
        )
    except ValueError as exc:
        parser.error(str(exc))

    if args.apply:
        write_plan(plan)

    if args.json:
        print(json.dumps(plan.to_dict(), indent=2, ensure_ascii=False))
    else:
        mode = "dry-run" if plan.dry_run else "apply"
        print(f"Telegram adapter installer plan: {plan.status} ({mode})")
        for item in plan.planned_files:
            print(f"- {item.path}: {item.description}")
    return 0 if not plan.errors else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
