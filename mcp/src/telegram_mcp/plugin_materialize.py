"""Materialize the canonical Telegram plugin package into the local Codex cache."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from .plugin_package import _iter_package_files, find_package_hygiene_issues


@dataclass(frozen=True)
class PluginMaterializeResult:
    status: str
    source_dir: str
    cache_dir: str
    version: str
    file_count: int
    hygiene_issues: list[str]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _read_plugin_version(plugin_root: Path) -> str:
    manifest = plugin_root / ".codex-plugin" / "plugin.json"
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    version = payload.get("version")
    if not isinstance(version, str) or not version.strip():
        raise ValueError(f"plugin version missing in {manifest}")
    return version.strip()


def materialize_plugin_cache(
    *,
    source_dir: str | Path,
    cache_root: str | Path,
) -> PluginMaterializeResult:
    source = Path(source_dir).expanduser().resolve()
    cache_base = Path(cache_root).expanduser().resolve()
    if not source.is_dir():
        raise FileNotFoundError(f"plugin source directory does not exist: {source}")

    issues = find_package_hygiene_issues(source)
    if issues:
        return PluginMaterializeResult(
            status="fail",
            source_dir=str(source),
            cache_dir=str(cache_base),
            version="",
            file_count=0,
            hygiene_issues=issues,
        )

    version = _read_plugin_version(source)
    cache_dir = cache_base / version
    cache_dir.mkdir(parents=True, exist_ok=True)

    copied = 0
    for source_file in _iter_package_files(source):
        relative = source_file.relative_to(source)
        target = cache_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_file, target)
        copied += 1

    return PluginMaterializeResult(
        status="ok",
        source_dir=str(source),
        cache_dir=str(cache_dir),
        version=version,
        file_count=copied,
        hygiene_issues=[],
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Materialize Telegram plugin package into Codex cache.")
    parser.add_argument("--source-dir", required=True)
    parser.add_argument("--cache-root", required=True)
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        result = materialize_plugin_cache(source_dir=args.source_dir, cache_root=args.cache_root)
    except (FileNotFoundError, ValueError) as exc:
        payload = {"status": "fail", "error": str(exc)}
        if args.json:
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            print(f"plugin materialize failed: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    else:
        print(f"plugin materialize: {result.status} ({result.file_count} files -> {result.cache_dir})")
        for issue in result.hygiene_issues:
            print(f"- {issue}", file=sys.stderr)

    return 0 if result.status == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())