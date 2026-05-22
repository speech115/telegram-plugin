"""Outbound media file path safety policy."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from .errors import ToolContractError

_BLOCKED_EXTENSIONS = {
    ".session",
    ".db",
    ".sqlite",
    ".sqlite3",
    ".tar",
    ".gz",
    ".tgz",
    ".zip",
    ".7z",
    ".rar",
    ".xz",
    ".bz2",
}

_CLOUD_SYNC_MARKERS = {
    "dropbox",
    "onedrive",
    "google drive",
    "icloud drive",
    "icloud~com~apple~clouddocs",
}


def _is_within(path: Path, roots: Iterable[Path]) -> bool:
    for root in roots:
        try:
            path.relative_to(root)
            return True
        except ValueError:
            continue
    return False


def _normalize_allowlist(allowlisted_dirs: Iterable[Path]) -> list[Path]:
    return [Path(item).expanduser().resolve(strict=False) for item in allowlisted_dirs]


def validate_outbound_media_path(
    file_path: str,
    *,
    allowlisted_dirs: Iterable[Path] = (),
) -> str:
    candidate_input = Path(file_path).expanduser()
    candidate = candidate_input.resolve(strict=False)
    allowlist = _normalize_allowlist(allowlisted_dirs)

    if _is_within(candidate, allowlist):
        return str(candidate)

    if candidate.is_dir():
        raise ToolContractError("unsafe_file_path", "Directories and repo roots are not allowed")

    name_lower = candidate.name.lower()
    if name_lower == ".env" or name_lower.startswith(".env."):
        raise ToolContractError("unsafe_file_path", "Environment files are blocked")

    if name_lower.endswith(".session"):
        raise ToolContractError("unsafe_file_path", "Session files are blocked")

    if candidate.suffix.lower() in _BLOCKED_EXTENSIONS:
        raise ToolContractError("unsafe_file_path", "Archive and database files are blocked")

    lowered_parts = [part.lower() for part in candidate.parts]
    if "tdata" in lowered_parts:
        raise ToolContractError("unsafe_file_path", "Telegram Desktop tdata paths are blocked")

    if any("subscribers" in part for part in lowered_parts):
        raise ToolContractError("unsafe_file_path", "Subscriber export artifacts are blocked")

    if any("checkpoint" in part for part in lowered_parts):
        raise ToolContractError("unsafe_file_path", "Checkpoint artifacts are blocked")

    if any(part.startswith(".") for part in candidate.parts[1:-1]):
        raise ToolContractError("unsafe_file_path", "Hidden runtime directories are blocked")

    if any(marker in part for part in lowered_parts for marker in _CLOUD_SYNC_MARKERS):
        raise ToolContractError("unsafe_file_path", "Cloud sync folders are blocked")

    home = Path.home().resolve(strict=False)
    if candidate == home:
        raise ToolContractError("unsafe_file_path", "Home root is blocked")
    try:
        rel_home = candidate.relative_to(home)
        if len(rel_home.parts) <= 2:
            raise ToolContractError("unsafe_file_path", "Broad home paths are blocked")
    except ValueError:
        pass

    cwd = Path.cwd().resolve(strict=False)
    if candidate == cwd or candidate == cwd.parent:
        raise ToolContractError("unsafe_file_path", "Repo roots are blocked")

    if candidate_input.is_symlink() or candidate.is_symlink():
        raise ToolContractError("unsafe_file_path", "Symlink paths are blocked")

    return str(candidate)
