"""Output locations for subscriber/member export artifacts."""

from __future__ import annotations

from pathlib import Path

def default_member_export_dir() -> Path:
    path = Path.home() / ".cache" / "telegram-mcp" / "member-exports"
    path.mkdir(parents=True, exist_ok=True)
    return path


def resolve_member_export_dir(output_dir: str | None) -> Path:
    candidate = default_member_export_dir() if output_dir is None else Path(output_dir).expanduser()
    resolved = candidate.resolve(strict=False)
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved
