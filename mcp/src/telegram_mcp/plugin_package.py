"""Build a portable Telegram Codex plugin package directory."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from .agent_doc_sync import check_agent_docs_sync, sync_agent_docs


FORBIDDEN_NAMES = {".DS_Store", ".env", "__pycache__"}
FORBIDDEN_SUFFIXES = {".session", ".pyc"}
PRIVATE_PATH_MARKERS = ("/Users/sereja", "Projects/.artifacts", "telegram-plugin-audit")


@dataclass(frozen=True)
class PluginPackageResult:
    status: str
    source_dir: str
    output_dir: str
    file_count: int
    hygiene_issues: list[str]
    agent_doc_sync: dict[str, object] | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def find_package_hygiene_issues(root: str | Path) -> list[str]:
    base = Path(root)
    issues: list[str] = []
    for path in sorted(base.rglob("*")):
        relative = path.relative_to(base)
        relative_text = str(relative)
        if path.name in FORBIDDEN_NAMES or path.suffix in FORBIDDEN_SUFFIXES:
            issues.append(f"{relative_text}: forbidden runtime artifact")
            continue
        if not path.is_file() or path.stat().st_size > 1_000_000:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if any(marker in text for marker in PRIVATE_PATH_MARKERS):
            issues.append(f"{relative_text}: hardcoded private path")
    return issues


def _iter_package_files(source_dir: Path) -> list[Path]:
    return [path for path in sorted(source_dir.rglob("*")) if path.is_file()]


def _default_mcp_repo() -> Path:
    return Path(__file__).resolve().parents[2]


def build_plugin_package(
    *,
    source_dir: str | Path,
    output_dir: str | Path,
    sync_agent_docs_to_mcp: bool = True,
    mcp_repo_dir: str | Path | None = None,
) -> PluginPackageResult:
    source = Path(source_dir).expanduser().resolve()
    output = Path(output_dir).expanduser()
    if not source.exists() or not source.is_dir():
        raise FileNotFoundError(f"plugin source directory does not exist: {source}")
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"output directory must be empty or missing: {output}")

    issues = find_package_hygiene_issues(source)
    if issues:
        return PluginPackageResult(
            status="fail",
            source_dir=str(source),
            output_dir=str(output),
            file_count=0,
            hygiene_issues=issues,
        )

    agent_doc_sync_payload: dict[str, object] | None = None
    manifest_path = source / "skills" / "telegram" / "agent-docs" / "manifest.json"
    if sync_agent_docs_to_mcp and manifest_path.is_file():
        sync_result = sync_agent_docs(
            source,
            mcp_repo_dir=mcp_repo_dir or _default_mcp_repo(),
            write_plugin_copy=True,
        )
        agent_doc_sync_payload = sync_result.to_dict()
    elif sync_agent_docs_to_mcp:
        agent_doc_sync_payload = {
            "status": "skipped",
            "reason": "agent-docs manifest missing",
            "manifest": str(manifest_path),
        }

    output.mkdir(parents=True, exist_ok=True)
    copied = 0
    for source_file in _iter_package_files(source):
        relative = source_file.relative_to(source)
        target = output / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_file, target)
        copied += 1

    return PluginPackageResult(
        status="ok",
        source_dir=str(source),
        output_dir=str(output),
        file_count=copied,
        hygiene_issues=[],
        agent_doc_sync=agent_doc_sync_payload,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a portable Telegram plugin package directory.")
    parser.add_argument("--source-dir", required=True, help="Plugin source directory to package.")
    parser.add_argument("--output-dir", required=True, help="Empty output directory for the package.")
    parser.add_argument("--json", action="store_true", help="Print a machine-readable result.")
    parser.add_argument(
        "--skip-agent-doc-sync",
        action="store_true",
        help="Do not regenerate docs/agent from plugin references before packaging.",
    )
    parser.add_argument(
        "--mcp-repo-dir",
        default=None,
        help="telegram-mcp repo root for docs/agent sync (defaults to this repository).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        result = build_plugin_package(
            source_dir=args.source_dir,
            output_dir=args.output_dir,
            sync_agent_docs_to_mcp=not args.skip_agent_doc_sync,
            mcp_repo_dir=args.mcp_repo_dir,
        )
    except (FileExistsError, FileNotFoundError) as exc:
        result = PluginPackageResult(
            status="fail",
            source_dir=args.source_dir,
            output_dir=args.output_dir,
            file_count=0,
            hygiene_issues=[str(exc)],
        )

    if args.json:
        print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    else:
        print(f"Telegram plugin package build: {result.status}")
        print(f"Files copied: {result.file_count}")
        for issue in result.hygiene_issues:
            print(f"- {issue}", file=sys.stderr)
    return 0 if result.status == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
