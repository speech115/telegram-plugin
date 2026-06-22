"""Attach in-process dialog read cache metadata to facade read payloads."""

from __future__ import annotations

import time
from typing import Any


def annotate_dialog_read_cache_meta(
    wrapper: Any,
    result: Any,
    *,
    cache_key: str,
    cache_hit: bool,
) -> Any:
    ttl = int(getattr(wrapper, "_dialog_read_cache_ttl", 0) or 0)
    if cache_hit:
        entry = getattr(wrapper, "_result_cache", {}).get(cache_key)
        age = round(time.monotonic() - entry[0], 3) if entry else 0.0
    else:
        age = 0.0
    result.result_cache_hit = cache_hit
    result.result_cache_age_seconds = age
    result.result_cache_ttl_seconds = ttl
    return result