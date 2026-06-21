from __future__ import annotations

from telegram_control_plane.api_gap_audit import audit_api_gaps


def test_api_gap_audit_classifies_new_telegram_capabilities() -> None:
    report = audit_api_gaps()

    assert report["status"] == "ok"
    by_id = {item["id"]: item for item in report["capabilities"]}
    assert by_id["bot_api_rich_messages"]["classification"] == "audit_only"
    assert by_id["bot_api_rich_messages"]["next_action"] == "track_changelog_only"
    assert by_id["thread_context"]["runtime_tools"] == [
        "list_forum_topics",
        "get_forum_topics_by_id",
        "get_discussion_message",
        "get_thread_replies",
    ]
    assert by_id["business_paid_media"]["classification"] == "blocked_by_permission_model"
    assert by_id["business_paid_media"]["next_action"] == "requires_explicit_business_write_policy"
    assert by_id["story_analytics"]["classification"] == "supported_runtime"
    assert report["summary"]["blocked_by_permission_model"] >= 1
