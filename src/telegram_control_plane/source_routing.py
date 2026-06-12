from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from .paths import CONTROL_ROOT, POLICY_DIR, TELECRAWL_ARCHIVE
from . import source_evidence, telecrawl_gap
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

DEFAULT_MATCHERS = {
    "live_intent": LIVE_INTENT_RE.pattern,
    "live_task": LIVE_TASK_RE.pattern,
    "archive_intent": ARCHIVE_INTENT_RE.pattern,
    "mirror_intent": MIRROR_INTENT_RE.pattern,
}


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


@dataclass(frozen=True)
class SourceRoutingPolicy:
    payload: dict[str, Any]

    @classmethod
    def load(cls) -> "SourceRoutingPolicy":
        return cls(load_source_routing_policy())

    @property
    def rules(self) -> dict[str, Any]:
        rules = self.payload.get("rules")
        return rules if isinstance(rules, dict) else {}

    @property
    def sources(self) -> dict[str, Any]:
        sources = self.payload.get("sources")
        return sources if isinstance(sources, dict) else {}

    @property
    def claims(self) -> dict[str, Any]:
        claims = self.payload.get("claims")
        return claims if isinstance(claims, dict) else {}

    def source_config(self, source_id: str) -> dict[str, Any]:
        return _source_config(self.payload, source_id)

    def matcher(self, matcher_id: str) -> re.Pattern[str]:
        matchers = self.payload.get("matchers") if isinstance(self.payload.get("matchers"), dict) else {}
        raw = matchers.get(matcher_id) if isinstance(matchers, dict) else None
        pattern = raw if isinstance(raw, str) and raw else DEFAULT_MATCHERS[matcher_id]
        return re.compile(pattern, re.IGNORECASE)

    def score_intent(self, intent: str) -> dict[str, int]:
        text = intent.strip().lower()
        scores: dict[str, int] = {}
        for source_id, config in self.sources.items():
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
                if self.matcher("live_intent").search(text):
                    score += 4
                if self.matcher("live_task").search(text):
                    score += 5
            if source_id == "telecrawl_archive" and self.matcher("archive_intent").search(text):
                score += 4
            if source_id == "telegram_mirror" and self.matcher("mirror_intent").search(text):
                score += 4
            if score:
                scores[source_id] = score
        return scores

    def recommend_route(
        self,
        intent: str,
        *,
        archive_ready: bool | None = None,
        archive_has_gaps: bool | None = None,
        mirror_preflight_ok: bool | None = None,
    ) -> dict[str, Any]:
        scores = self.score_intent(intent)
        live_score = scores.get("live_mcp", 0)
        archive_score = scores.get("telecrawl_archive", 0)
        mirror_score = scores.get("telegram_mirror", 0)

        evidence_rules = source_evidence.source_evidence_rules(
            source_routing_policy=self.payload,
            telecrawl_policy=telecrawl_gap.load_telecrawl_policy(),
        )
        if live_score > 0 and (live_score >= archive_score and live_score >= mirror_score):
            primary = "live_mcp"
        elif archive_score > mirror_score and archive_score > 0:
            primary = "telecrawl_archive"
        elif mirror_score > 0:
            primary = "telegram_mirror"
        else:
            primary = evidence_rules.live_route_target

        blocked: list[str] = []
        warnings: list[str] = []
        if primary == "live_mcp":
            blocked.extend(evidence_rules.live_blocked_sources)
        if primary == "telecrawl_archive":
            if archive_ready is False:
                warnings.append("archive_not_ready")
            if archive_has_gaps is True:
                warnings.append("archive_has_known_gaps")
            if evidence_rules.telecrawl_blocks_current_claims:
                warnings.append("do_not_use_for_current_claims")
        if primary == "telegram_mirror" and mirror_preflight_ok is False:
            warnings.append("mirror_preflight_required")

        live_cfg = self.source_config("live_mcp")
        primary_cfg = self.source_config(primary)
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
            "negative_archive_claim": evidence_rules.negative_archive_claim,
            "policy_path": str(SOURCE_ROUTING_PATH),
        }

    def audit(self) -> dict[str, Any]:
        telecrawl_policy = telecrawl_gap.load_telecrawl_policy()
        evidence_rules = source_evidence.source_evidence_rules(
            source_routing_policy=self.payload,
            telecrawl_policy=telecrawl_policy,
        )
        findings: list[dict[str, Any]] = evidence_rules.audit_findings()
        for phrase in (
            "что нового за сегодня в чате",
            "прочитай переписку за сегодня",
            "latest in chat",
        ):
            sample = self.recommend_route(phrase)
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
            "rules": self.rules,
            "sources": sorted(self.sources.keys()),
            "telecrawl_archive_cli": str(TELECRAWL_ARCHIVE),
            "sample_routes": {
                "today": self.recommend_route("что нового за сегодня"),
                "archive_search": self.recommend_route("найди в архиве упоминания docker"),
                "mirror": self.recommend_route("mirror allowlist export preflight"),
            },
        }


def _routing_policy(policy: dict[str, Any] | None = None) -> SourceRoutingPolicy:
    return SourceRoutingPolicy(policy if policy is not None else load_source_routing_policy())


def score_intent(intent: str, *, policy: dict[str, Any] | None = None) -> dict[str, int]:
    return _routing_policy(policy).score_intent(intent)


def recommend_route(
    intent: str,
    *,
    policy: dict[str, Any] | None = None,
    archive_ready: bool | None = None,
    archive_has_gaps: bool | None = None,
    mirror_preflight_ok: bool | None = None,
) -> dict[str, Any]:
    return _routing_policy(policy).recommend_route(
        intent,
        archive_ready=archive_ready,
        archive_has_gaps=archive_has_gaps,
        mirror_preflight_ok=mirror_preflight_ok,
    )


def audit_source_routing() -> dict[str, Any]:
    return SourceRoutingPolicy.load().audit()
