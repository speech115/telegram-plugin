from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from .paths import CONTROL_ROOT, POLICY_DIR, TELECRAWL_ARCHIVE
from . import telecrawl_gap
from .util import load_json, status_from_findings

SOURCE_ROUTING_PATH = POLICY_DIR / "source-routing.json"

LIVE_INTENT_RE = re.compile(
    r"\b(today|recent|latest|current|live|now|сегодня|новое|последн|сейчас)\b",
    re.IGNORECASE,
)
LIVE_TASK_RE = re.compile(
    r"\b(send|reply|media|voice|draft|photo|video|отправ|ответ|голос)\b",
    re.IGNORECASE,
)
ARCHIVE_INTENT_RE = re.compile(
    r"\b(archive|historical|архив|истор|прошл|search-all|coverage)\b",
    re.IGNORECASE,
)
MIRROR_INTENT_RE = re.compile(r"\b(mirror|allowlist|зеркал|recovery|preflight)\b", re.IGNORECASE)


@lru_cache(maxsize=4)
def load_source_routing_policy(path: str = str(SOURCE_ROUTING_PATH)) -> dict[str, Any]:
    payload = load_json(Path(path)) or {}
    if not isinstance(payload.get("sources"), dict):
        payload["sources"] = {}
    return payload


def clear_policy_cache() -> None:
    load_source_routing_policy.cache_clear()


def _source_config(policy: dict[str, Any], source_id: str) -> dict[str, Any]:
    sources = policy.get("sources")
    if not isinstance(sources, dict):
        return {}
    item = sources.get(source_id)
    return item if isinstance(item, dict) else {}


def score_intent(intent: str, *, policy: dict[str, Any] | None = None) -> dict[str, int]:
    payload = policy if policy is not None else load_source_routing_policy()
    text = intent.strip().lower()
    scores: dict[str, int] = {}
    for source_id, config in payload.get("sources", {}).items():
        if not isinstance(source_id, str) or not isinstance(config, dict):
            continue
        score = 0
        for keyword in config.get("intent_keywords", []):
            if isinstance(keyword, str) and keyword.lower() in text:
                score += 2
        for keyword in config.get("task_keywords", []):
            if isinstance(keyword, str) and keyword.lower() in text:
                score += 3
        if source_id == "live_mcp":
            if LIVE_INTENT_RE.search(text):
                score += 4
            if LIVE_TASK_RE.search(text):
                score += 5
        if source_id == "telecrawl_archive" and ARCHIVE_INTENT_RE.search(text):
            score += 4
        if source_id == "telegram_mirror" and MIRROR_INTENT_RE.search(text):
            score += 4
        if score:
            scores[source_id] = score
    return scores


def recommend_route(
    intent: str,
    *,
    policy: dict[str, Any] | None = None,
    archive_ready: bool | None = None,
    archive_has_gaps: bool | None = None,
    mirror_preflight_ok: bool | None = None,
) -> dict[str, Any]:
    payload = policy if policy is not None else load_source_routing_policy()
    rules = payload.get("rules") if isinstance(payload.get("rules"), dict) else {}
    scores = score_intent(intent, policy=payload)
    live_score = scores.get("live_mcp", 0)
    archive_score = scores.get("telecrawl_archive", 0)
    mirror_score = scores.get("telegram_mirror", 0)

    if live_score > 0 and (live_score >= archive_score and live_score >= mirror_score):
        primary = "live_mcp"
    elif archive_score > mirror_score and archive_score > 0:
        primary = "telecrawl_archive"
    elif mirror_score > 0:
        primary = "telegram_mirror"
    else:
        primary = str(rules.get("route_current_latest_today_send_reply_media_to") or "live_mcp")

    blocked: list[str] = []
    warnings: list[str] = []
    if primary == "live_mcp":
        never = rules.get("never_route_live_intents_to")
        if isinstance(never, list):
            blocked.extend(str(item) for item in never if isinstance(item, str))
    if primary == "telecrawl_archive":
        if archive_ready is False:
            warnings.append("archive_not_ready")
        if archive_has_gaps is True:
            warnings.append("archive_has_known_gaps")
        telecrawl_policy = telecrawl_gap.load_telecrawl_policy()
        if telecrawl_policy.get("known_gaps_are_blocking_for_current_claims"):
            warnings.append("do_not_use_for_current_claims")
    if primary == "telegram_mirror" and mirror_preflight_ok is False:
        warnings.append("mirror_preflight_required")

    live_cfg = _source_config(payload, "live_mcp")
    primary_cfg = _source_config(payload, primary)
    return {
        "intent": intent,
        "primary_source": primary,
        "scores": scores,
        "blocked_sources": blocked,
        "warnings": warnings,
        "tools_first": primary_cfg.get("tools_first") if isinstance(primary_cfg.get("tools_first"), list) else [],
        "backend": primary_cfg.get("backend"),
        "description": primary_cfg.get("description"),
        "fallback_live_tools": live_cfg.get("tools_first") if isinstance(live_cfg.get("tools_first"), list) else [],
        "negative_archive_claim": (payload.get("claims") or {}).get("negative_archive_results"),
        "policy_path": str(SOURCE_ROUTING_PATH),
    }


def audit_source_routing() -> dict[str, Any]:
    policy = load_source_routing_policy()
    telecrawl_policy = telecrawl_gap.load_telecrawl_policy()
    findings: list[dict[str, Any]] = []
    rules = policy.get("rules") if isinstance(policy.get("rules"), dict) else {}
    live_route = rules.get("route_current_latest_today_send_reply_media_to")
    telecrawl_route = telecrawl_policy.get("route_current_latest_today_send_reply_media_to")
    if live_route and telecrawl_route and live_route != telecrawl_route:
        findings.append(
            {
                "id": "source_routing_live_route_mismatch",
                "severity": "blocking",
                "message": "source-routing and telecrawl policies disagree on live route target.",
                "source_routing": live_route,
                "telecrawl": telecrawl_route,
            }
        )
    if telecrawl_policy.get("negative_results_claim") != (policy.get("claims") or {}).get("negative_archive_results"):
        findings.append(
            {
                "id": "source_routing_negative_claim_mismatch",
                "severity": "warn",
                "message": "Archive negative-results claim differs between source-routing and telecrawl policy.",
            }
        )
    for source_id in ("live_mcp", "telecrawl_archive", "telegram_mirror"):
        if source_id not in policy.get("sources", {}):
            findings.append(
                {
                    "id": "source_routing_missing_source",
                    "severity": "blocking",
                    "source": source_id,
                    "message": "Source routing policy is missing a required source definition.",
                }
            )
    for phrase in (
        "что нового за сегодня в чате",
        "прочитай переписку за сегодня",
        "latest in chat",
    ):
        sample = recommend_route(phrase)
        if sample.get("primary_source") != "live_mcp":
            findings.append(
                {
                    "id": "source_routing_live_sample_misrouted",
                    "severity": "blocking",
                    "message": f"Today/live phrase routed to {sample.get('primary_source')!r}, not live_mcp.",
                    "sample": sample,
                }
            )
        blocked = sample.get("blocked_sources") if isinstance(sample.get("blocked_sources"), list) else []
        if "telecrawl_archive" not in blocked:
            findings.append(
                {
                    "id": "source_routing_archive_not_blocked",
                    "severity": "blocking",
                    "message": "Live route must block telecrawl_archive for today intents.",
                    "sample": sample,
                }
            )
    return {
        "status": status_from_findings(findings),
        "findings": findings,
        "policy_path": str(SOURCE_ROUTING_PATH),
        "rules": rules,
        "sources": sorted(policy.get("sources", {}).keys()),
        "telecrawl_archive_cli": str(TELECRAWL_ARCHIVE),
        "sample_routes": {
            "today": recommend_route("что нового за сегодня"),
            "archive_search": recommend_route("найди в архиве упоминания docker"),
            "mirror": recommend_route("mirror allowlist export preflight"),
        },
    }