from __future__ import annotations

from telegram_control_plane.source_routing import (
    audit_source_routing,
    recommend_route,
    score_intent,
)


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