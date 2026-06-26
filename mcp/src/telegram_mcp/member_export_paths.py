"""Output locations for subscriber/member export artifacts."""

from __future__ import annotations

from pathlib import Path

def default_member_export_dir() -> Path:
    path = Path.home() / ".cache" / "telegram-mcp" / "member-exports"
    path.mkdir(parents=True, exist_ok=True)
    path.chmod(0o700)
    return path


def resolve_member_export_dir(output_dir: str | None) -> Path:
    root = default_member_export_dir().resolve(strict=False)
    candidate = root if output_dir is None else Path(output_dir).expanduser()
    resolved = candidate.resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(
            f"member export output_dir must stay under the private export root: {root}"
        ) from exc
    resolved.mkdir(parents=True, exist_ok=True)
    resolved.chmod(0o700)
    return resolved
