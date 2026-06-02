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
HOSTS = ("codex", "claude", "opencode", "standalone")


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
        elif host == "claude":
            planned.append(_claude_adapter(endpoint, token_env))
        elif host == "opencode":
            planned.append(_opencode_adapter(endpoint, token_env))
        elif host == "standalone":
            planned.append(_standalone_skill_adapter())

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
