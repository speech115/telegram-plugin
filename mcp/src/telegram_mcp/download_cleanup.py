"""Retention cleanup for locally downloaded Telegram media."""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from .config import get_settings


@dataclass(frozen=True)
class DownloadCleanupResult:
    enabled: bool = False
    dry_run: bool = True
    download_dir: str = ""
    retention_days: int = 0
    candidate_files: int = 0
    candidate_bytes: int = 0
    deleted_files: int = 0
    deleted_bytes: int = 0
    errors: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def estimate_download_cleanup(
    download_dir: Path,
    retention_days: int,
    *,
    now: float | None = None,
) -> DownloadCleanupResult:
    """Return a read-only estimate for old top-level download files."""
    return _scan_download_dir(
        download_dir,
        retention_days,
        delete=False,
        now=now,
    )


def cleanup_download_dir(
    download_dir: Path,
    retention_days: int,
    *,
    now: float | None = None,
) -> DownloadCleanupResult:
    """Delete old top-level files from the Telegram download directory."""
    return _scan_download_dir(
        download_dir,
        retention_days,
        delete=True,
        now=now,
    )


def _scan_download_dir(
    download_dir: Path,
    retention_days: int,
    *,
    delete: bool,
    now: float | None,
) -> DownloadCleanupResult:
    if retention_days <= 0 or not download_dir.exists():
        return DownloadCleanupResult(
            enabled=retention_days > 0,
            dry_run=not delete,
            download_dir=str(download_dir),
            retention_days=retention_days,
        )

    cutoff = (time.time() if now is None else now) - retention_days * 24 * 60 * 60
    candidate_files = 0
    candidate_bytes = 0
    deleted_files = 0
    deleted_bytes = 0
    errors: list[str] = []

    try:
        entries = list(download_dir.iterdir())
    except OSError as exc:
        return DownloadCleanupResult(
            enabled=True,
            dry_run=not delete,
            download_dir=str(download_dir),
            retention_days=retention_days,
            errors=(f"{download_dir}: {type(exc).__name__}: {exc}",),
        )

    for entry in entries:
        try:
            if entry.is_symlink() or not entry.is_file():
                continue
            stat = entry.stat()
            if stat.st_mtime >= cutoff:
                continue
            candidate_files += 1
            candidate_bytes += stat.st_size
            if delete:
                entry.unlink()
                deleted_files += 1
                deleted_bytes += stat.st_size
        except OSError as exc:
            errors.append(f"{entry}: {type(exc).__name__}: {exc}")

    return DownloadCleanupResult(
        enabled=True,
        dry_run=not delete,
        download_dir=str(download_dir),
        retention_days=retention_days,
        candidate_files=candidate_files,
        candidate_bytes=candidate_bytes,
        deleted_files=deleted_files,
        deleted_bytes=deleted_bytes,
        errors=tuple(errors),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Inspect or delete old top-level Telegram media downloads.",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Only report candidates.")
    mode.add_argument("--delete", action="store_true", help="Delete candidates.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args(argv)

    settings = get_settings()
    settings.ensure_dirs()

    if args.delete:
        result = cleanup_download_dir(
            settings.download_dir,
            settings.download_retention_days,
        )
    else:
        result = estimate_download_cleanup(
            settings.download_dir,
            settings.download_retention_days,
        )

    payload = result.to_dict()
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        action = "delete" if args.delete else "dry-run"
        print(
            f"{action}: {payload['candidate_files']} candidate files, "
            f"{payload['candidate_bytes']} bytes; "
            f"deleted {payload['deleted_files']} files, "
            f"{payload['deleted_bytes']} bytes"
        )
    return 1 if result.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
