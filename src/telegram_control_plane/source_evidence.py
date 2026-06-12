from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .paths import POLICY_DIR
from .util import load_json

SOURCE_ROUTING_PATH = POLICY_DIR / "source-routing.json"
TELECRAWL_POLICY_PATH = POLICY_DIR / "telecrawl.json"

REQUIRED_SOURCE_IDS = frozenset({"live_mcp", "telecrawl_archive", "telegram_mirror"})


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


@dataclass(frozen=True)
class SourceEvidenceRules:
    """Domain rules for choosing live, archive, and mirror evidence sources."""

    source_routing_policy: dict[str, Any]
    telecrawl_policy: dict[str, Any]

    @classmethod
    def load(
        cls,
        *,
        source_routing_path: Path = SOURCE_ROUTING_PATH,
        telecrawl_policy_path: Path = TELECRAWL_POLICY_PATH,
    ) -> "SourceEvidenceRules":
        return cls(
            source_routing_policy=load_json(source_routing_path) or {},
            telecrawl_policy=load_json(telecrawl_policy_path) or {},
        )

    @property
    def rules(self) -> dict[str, Any]:
        return _dict(self.source_routing_policy.get("rules"))

    @property
    def sources(self) -> dict[str, Any]:
        return _dict(self.source_routing_policy.get("sources"))

    @property
    def claims(self) -> dict[str, Any]:
        return _dict(self.source_routing_policy.get("claims"))

    @property
    def live_route_target(self) -> str:
        target = self.rules.get("route_current_latest_today_send_reply_media_to")
        return str(target) if isinstance(target, str) and target else "live_mcp"

    @property
    def live_blocked_sources(self) -> list[str]:
        return [str(item) for item in _list(self.rules.get("never_route_live_intents_to")) if isinstance(item, str)]

    @property
    def negative_archive_claim(self) -> str | None:
        claim = self.claims.get("negative_archive_results")
        return claim if isinstance(claim, str) and claim else None

    @property
    def never_infer_absence_from_archive_only(self) -> bool:
        return self.claims.get("never_infer_absence_from_archive_only") is True

    @property
    def telecrawl_is_archive_evidence(self) -> bool:
        return (
            self.telecrawl_policy.get("is_live") is False
            and self.telecrawl_policy.get("classification") == "archive_snapshot"
        )

    @property
    def telecrawl_blocks_current_claims(self) -> bool:
        return self.telecrawl_policy.get("known_gaps_are_blocking_for_current_claims") is True

    def audit_findings(self) -> list[dict[str, Any]]:
        findings: list[dict[str, Any]] = []
        missing_sources = sorted(REQUIRED_SOURCE_IDS - set(self.sources))
        if missing_sources:
            findings.append(
                {
                    "id": "source_evidence_missing_source",
                    "severity": "blocking",
                    "sources": missing_sources,
                    "message": "Source evidence policy is missing required source definitions.",
                }
            )
        if self.live_route_target != "live_mcp":
            findings.append(
                {
                    "id": "source_evidence_live_route_not_live_mcp",
                    "severity": "blocking",
                    "route": self.live_route_target,
                    "message": "Current/latest/today/send/media claims must route to live_mcp.",
                }
            )
        if "telecrawl_archive" not in self.live_blocked_sources:
            findings.append(
                {
                    "id": "source_evidence_archive_not_blocked_for_live",
                    "severity": "blocking",
                    "message": "Live/current intents must explicitly block telecrawl_archive.",
                }
            )
        if not self.telecrawl_is_archive_evidence:
            findings.append(
                {
                    "id": "source_evidence_telecrawl_not_archive",
                    "severity": "blocking",
                    "message": "Telecrawl must be classified as non-live archive evidence.",
                }
            )
        if not self.telecrawl_blocks_current_claims:
            findings.append(
                {
                    "id": "source_evidence_telecrawl_allows_current_claims",
                    "severity": "blocking",
                    "message": "Telecrawl gaps must block current/latest completeness claims.",
                }
            )
        if not self.negative_archive_claim:
            findings.append(
                {
                    "id": "source_evidence_missing_negative_archive_claim",
                    "severity": "warn",
                    "message": "Archive negative-results wording is missing from source evidence claims.",
                }
            )
        if not self.never_infer_absence_from_archive_only:
            findings.append(
                {
                    "id": "source_evidence_archive_absence_not_guarded",
                    "severity": "warn",
                    "message": "Archive evidence must not imply global absence from Telegram.",
                }
            )
        return findings


def source_evidence_rules(
    *,
    source_routing_policy: dict[str, Any] | None = None,
    telecrawl_policy: dict[str, Any] | None = None,
) -> SourceEvidenceRules:
    return SourceEvidenceRules(
        source_routing_policy=(
            source_routing_policy
            if source_routing_policy is not None
            else load_json(SOURCE_ROUTING_PATH) or {}
        ),
        telecrawl_policy=telecrawl_policy if telecrawl_policy is not None else load_json(TELECRAWL_POLICY_PATH) or {},
    )
