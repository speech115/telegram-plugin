from __future__ import annotations

import json
from pathlib import Path

from telegram_control_plane.skill_behavior import (
    decide_media_action,
    decide_paging_action,
    decide_voice_action,
    decide_write_action,
    plugin_surface_findings,
)


ROOT = Path(__file__).resolve().parents[1]


def test_draft_reply_intent_never_sends() -> None:
    positive = decide_write_action("подготовь ответ: принял")
    negative = decide_write_action(
        "отправь: принял",
        stable_target=True,
        exact_text=True,
    )

    assert positive.action == "draft_only"
    assert positive.may_send is False
    assert negative.action == "direct_send"
    assert negative.may_send is True


def test_explicit_send_requires_stable_target_and_exact_text() -> None:
    positive = decide_write_action(
        "отправь: принял в @target",
        stable_target=True,
        exact_text=True,
    )
    fuzzy = decide_write_action("send him ok", stable_target=False, exact_text=True)

    assert positive.action == "direct_send"
    assert positive.may_send is True
    assert fuzzy.action == "ask_for_stable_target_or_text"
    assert fuzzy.may_send is False


def test_preview_to_send_requires_same_turn_unchanged_preview() -> None:
    positive = decide_write_action(
        "send it",
        same_turn_preview=True,
        preview_unchanged=True,
        confirmation_token=True,
    )
    stale = decide_write_action("send it", same_turn_preview=False, preview_unchanged=True)

    assert positive.action == "confirmed_send"
    assert positive.may_send is True
    assert stale.action == "prepare_again"
    assert stale.may_send is False


def test_media_visual_answers_require_downloaded_file_evidence() -> None:
    positive = decide_media_action(
        asks_visual_question=True,
        has_scoped_message_ids=True,
        downloaded_files_available=True,
    )
    metadata_only = decide_media_action(
        asks_visual_question=True,
        has_scoped_message_ids=True,
        downloaded_files_available=False,
    )

    assert positive.action == "inspect_downloaded_files"
    assert positive.may_answer_visual_content is True
    assert metadata_only.action == "download_selected_media"
    assert metadata_only.may_answer_visual_content is False


def test_voice_handling_uses_builtin_or_blocks_external_services() -> None:
    positive = decide_voice_action(
        voice_could_affect_answer=True,
        builtin_transcript_available=True,
    )
    no_approval = decide_voice_action(
        voice_could_affect_answer=True,
        builtin_transcript_available=False,
        explicit_external_approval=False,
    )

    assert positive.action == "use_builtin_voice_transcription"
    assert positive.may_use_external_service is False
    assert no_approval.action == "call_transcribe_voice_or_report_gap"
    assert no_approval.may_use_external_service is False


def test_complete_context_pages_only_when_completeness_was_requested() -> None:
    positive = decide_paging_action(
        user_asked_complete_context=True,
        has_more_before=True,
    )
    bounded = decide_paging_action(
        user_asked_complete_context=False,
        truncated=True,
    )

    assert positive.action == "page_same_mcp_tool"
    assert bounded.action == "report_remaining_truncation"


def test_portable_plugin_exposes_full_surface_without_allowed_tools() -> None:
    config = json.loads((ROOT / "generated/telegram-plugin-package/.mcp.json").read_text())
    broken = {
        "mcpServers": {
            "telegram-main": {
                "url": "http://127.0.0.1:8799/mcp",
                "allowedTools": ["telegram_read"],
                "note": "restricted facade",
            }
        }
    }

    assert plugin_surface_findings(config) == []
    assert plugin_surface_findings(broken) == [
        "telegram-main:legacy_allowlist",
        "telegram-main:missing_full_surface_note",
    ]
