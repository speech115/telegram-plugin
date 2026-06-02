"""Safe output locations for subscriber/member export artifacts."""

from __future__ import annotations

from pathlib import Path

from .errors import ToolContractError

_CLOUD_SYNC_MARKERS = {
    "dropbox",
    "onedrive",
    "google drive",
    "icloud drive",
    "icloud~com~apple~clouddocs",
}


def default_member_export_dir() -> Path:
    path = Path.home() / ".cache" / "telegram-mcp" / "member-exports"
    path.mkdir(parents=True, exist_ok=True)
    return path


def resolve_member_export_dir(output_dir: str | None) -> Path:
    candidate = default_member_export_dir() if output_dir is None else Path(output_dir).expanduser()
    resolved = candidate.resolve(strict=False)
    if resolved.is_dir() and any((parent / ".git").exists() for parent in (resolved, *resolved.parents)):
        raise ToolContractError(
            "unsafe_member_export_path",
            "Refusing to write member exports into a git working tree; use a private cache directory.",
        )
    lowered_parts = [part.lower() for part in resolved.parts]
    if any(marker in part for part in lowered_parts for marker in _CLOUD_SYNC_MARKERS):
        raise ToolContractError(
            "unsafe_member_export_path",
            "Cloud-synced directories are blocked for member export artifacts.",
        )
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved