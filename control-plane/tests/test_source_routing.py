from __future__ import annotations

from telegram_control_plane.source_routing import (
    SourceRoutingPolicy,
    audit_source_routing,
    recommend_route,
    score_intent,
)
from telegram_control_plane.source_evidence import source_evidence_rules


def test_today_intent_routes_live_mcp() -> None:
    route = recommend_route("что нового за сегодня в чате")
    assert route["primary_source"] == "live_mcp"
    assert "tg" in route["tools_first"]


def test_archive_intent_routes_telecrawl() -> None:
    scores = score_intent("найди в архиве упоминания docker за прошлый год")
    assert scores.get("telecrawl_archive", 0) >= scores.get("live_mcp", 0)
    route = recommend_route("найди в архиве упоминания docker")
    assert route["primary_source"] == "telecrawl_archive"


def test_send_task_routes_live_mcp() -> None:
    route = recommend_route("отправь ответ в чат")
    assert route["primary_source"] == "live_mcp"


def test_audit_source_routing_passes() -> None:
    report = audit_source_routing()
    assert report["status"] == "ok"
    assert "live_mcp" in report["sources"]


def test_today_intents_never_route_to_archive_or_mirror() -> None:
    samples = [
        "что нового за сегодня",
        "прочитай чат за today",
        "latest messages in chat",
        "что писали сегодня",
    ]
    for intent in samples:
        route = recommend_route(intent)
        assert route["primary_source"] == "live_mcp", intent
        assert "telecrawl_archive" in route.get("blocked_sources", [])


def test_live_intent_scores_beat_archive_for_today_phrase() -> None:
    scores = score_intent("что нового за сегодня в чате")
    assert scores.get("live_mcp", 0) > scores.get("telecrawl_archive", 0)


def test_source_routing_policy_matchers_are_policy_backed() -> None:
    policy = SourceRoutingPolicy(
        {
            "sources": {
                "live_mcp": {"intent_keywords": [], "task_keywords": []},
                "telecrawl_archive": {"intent_keywords": [], "task_keywords": []},
                "telegram_mirror": {"intent_keywords": [], "task_keywords": []},
            },
            "rules": {"route_current_latest_today_send_reply_media_to": "live_mcp"},
            "matchers": {
                "live_intent": "fresh-only",
                "live_task": "send",
                "archive_intent": "archive",
                "mirror_intent": "mirror",
            },
        }
    )

    assert policy.score_intent("fresh-only updates")["live_mcp"] == 4
    assert score_intent("fresh-only updates", policy=policy.payload)["live_mcp"] == 4


def test_route_warnings_include_unready_archive_and_mirror_preflight() -> None:
    archive = recommend_route("найди в архиве docker", archive_ready=False, archive_has_gaps=True)
    assert archive["primary_source"] == "telecrawl_archive"
    assert {"archive_not_ready", "archive_has_known_gaps", "do_not_use_for_current_claims"}.issubset(
        archive["warnings"]
    )

    mirror = recommend_route("mirror allowlist export", mirror_preflight_ok=False)
    assert mirror["primary_source"] == "telegram_mirror"
    assert "mirror_preflight_required" in mirror["warnings"]


def test_source_evidence_rules_own_live_archive_invariant() -> None:
    rules = source_evidence_rules()

    assert rules.live_route_target == "live_mcp"
    assert "telecrawl_archive" in rules.live_blocked_sources
    assert rules.telecrawl_is_archive_evidence is True
    assert rules.telecrawl_blocks_current_claims is True
    assert rules.negative_archive_claim == "no matches in this archive coverage"
    assert rules.audit_findings() == []


def test_ambiguous_route_fallback_uses_source_evidence_rules() -> None:
    policy = {
        "sources": {
            "live_mcp": {"tools_first": ["live"]},
            "telecrawl_archive": {"tools_first": ["archive"]},
            "telegram_mirror": {"tools_first": ["mirror"]},
        },
        "rules": {
            "route_current_latest_today_send_reply_media_to": "telegram_mirror",
            "never_route_live_intents_to": ["telecrawl_archive"],
        },
        "claims": {"negative_archive_results": "fixture", "never_infer_absence_from_archive_only": True},
    }

    route = SourceRoutingPolicy(policy).recommend_route("без явного intent")

    assert route["primary_source"] == source_evidence_rules(source_routing_policy=policy).live_route_target


def test_source_routing_audit_uses_single_missing_source_finding() -> None:
    policy = SourceRoutingPolicy(
        {
            "sources": {"live_mcp": {}},
            "rules": {
                "route_current_latest_today_send_reply_media_to": "live_mcp",
                "never_route_live_intents_to": ["telecrawl_archive"],
            },
            "claims": {"negative_archive_results": "same", "never_infer_absence_from_archive_only": True},
        }
    )

    report = policy.audit()
    missing = [item for item in report["findings"] if "missing_source" in item["id"]]

    assert missing == [
        {
            "id": "source_evidence_missing_source",
            "severity": "blocking",
            "sources": ["telecrawl_archive", "telegram_mirror"],
            "message": "Source evidence policy is missing required source definitions.",
        }
    ]


def test_source_routing_audit_flags_live_route_not_live_mcp() -> None:
    policy = SourceRoutingPolicy(
        {
            "sources": {"live_mcp": {}, "telecrawl_archive": {}, "telegram_mirror": {}},
            "rules": {"route_current_latest_today_send_reply_media_to": "telecrawl_archive"},
            "claims": {"negative_archive_results": "same"},
        }
    )

    report = policy.audit()

    assert report["status"] == "fail"
    assert any(item["id"] == "source_evidence_live_route_not_live_mcp" for item in report["findings"])
