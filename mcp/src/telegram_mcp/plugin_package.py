"""Build a portable Telegram Codex plugin package directory."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from dataclasses import asdict, dataclass
from pathlib import Path


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


def build_plugin_package(*, source_dir: str | Path, output_dir: str | Path) -> PluginPackageResult:
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
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a portable Telegram plugin package directory.")
    parser.add_argument("--source-dir", required=True, help="Plugin source directory to package.")
    parser.add_argument("--output-dir", required=True, help="Empty output directory for the package.")
    parser.add_argument("--json", action="store_true", help="Print a machine-readable result.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        result = build_plugin_package(source_dir=args.source_dir, output_dir=args.output_dir)
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
