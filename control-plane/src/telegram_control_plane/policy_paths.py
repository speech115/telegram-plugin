"""Resolve managed-system policy path placeholders."""

from __future__ import annotations

import os
import re
from pathlib import Path

_POLICY_PATH_RE = re.compile(r"^\$\{([^:}]+)(?::-([^}]*))?\}$")


def resolve_policy_path(raw: str) -> Path:
    """Expand ${ENV:-default} placeholders used in policy JSON."""
    text = raw.strip()
    match = _POLICY_PATH_RE.match(text)
    if not match:
        return Path(text).expanduser()
    name, default = match.group(1), match.group(2) or ""
    value = os.environ.get(name, default)
    return Path(value).expanduser()