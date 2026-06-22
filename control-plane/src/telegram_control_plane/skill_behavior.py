from __future__ import annotations

from dataclasses import dataclass
from typing import Any


DRAFT_MARKERS = ("draft", "prepare", "подготов", "наброс", "что ответ")
PREVIEW_MARKERS = ("preview", "покажи перед", "проверь текст")
SEND_MARKERS = ("send", "send it", "отправ", "reply")


@dataclass(frozen=True)
class WriteDecision:
    action: str
    may_send: bool
    reason: str


def decide_write_action(
    text: str,
    *,
    stable_target: bool = False,
    exact_text: bool = False,
    same_turn_preview: bool = False,
    preview_unchanged: bool = False,
    confirmation_token: bool = False,
) -> WriteDecision:
    normalized = text.casefold()
    if any(marker in normalized for marker in DRAFT_MARKERS):
        return WriteDecision("draft_only", False, "draft_intent_never_sends")
    if any(marker in normalized for marker in PREVIEW_MARKERS):
        return WriteDecision("preview_only", False, "preview_intent_never_sends")
    if "send it" in normalized:
        if same_turn_preview and preview_unchanged:
            action = "confirmed_send" if confirmation_token else "direct_send"
            return WriteDecision(action, True, "same_turn_preview_unchanged")
        return WriteDecision("prepare_again", False, "stale_or_changed_preview")
    if any(marker in normalized for marker in SEND_MARKERS):
        if stable_target and exact_text:
            return WriteDecision("direct_send", True, "stable_target_and_exact_text")
        return WriteDecision("ask_for_stable_target_or_text", False, "write_hard_stop")
    return WriteDecision("no_write", False, "no_write_intent")


@dataclass(frozen=True)
class MediaDecision:
    action: str
    may_answer_visual_content: bool
    reason: str


def decide_media_action(
    *,
    asks_visual_question: bool,
    has_scoped_message_ids: bool = False,
    downloaded_files_available: bool = False,
) -> MediaDecision:
    if not asks_visual_question:
        return MediaDecision("text_only", True, "no_visual_claim_requested")
    if not has_scoped_message_ids:
        return MediaDecision("collect_scoped_media_ids", False, "message_ids_required")
    if not downloaded_files_available:
        return MediaDecision("download_selected_media", False, "local_file_required")
    return MediaDecision("inspect_downloaded_files", True, "actual_file_evidence")


@dataclass(frozen=True)
class VoiceDecision:
    action: str
    may_use_external_service: bool
    reason: str


def decide_voice_action(
    *,
    voice_could_affect_answer: bool,
    builtin_transcript_available: bool = False,
    explicit_external_approval: bool = False,
) -> VoiceDecision:
    if not voice_could_affect_answer:
        return VoiceDecision("skip_voice_transcription", False, "voice_not_needed")
    if builtin_transcript_available:
        return VoiceDecision("use_builtin_voice_transcription", False, "telegram_mcp_transcript")
    if explicit_external_approval:
        return VoiceDecision("external_transcription_allowed", True, "explicit_user_approval")
    return VoiceDecision("call_transcribe_voice_or_report_gap", False, "external_services_blocked")


@dataclass(frozen=True)
class PagingDecision:
    action: str
    reason: str


def decide_paging_action(
    *,
    user_asked_complete_context: bool,
    has_more_before: bool = False,
    truncated: bool = False,
) -> PagingDecision:
    if user_asked_complete_context and (has_more_before or truncated):
        return PagingDecision("page_same_mcp_tool", "complete_context_requested")
    if has_more_before or truncated:
        return PagingDecision("report_remaining_truncation", "not_exhaustive_request")
    return PagingDecision("summarize_current_window", "window_complete")


def plugin_surface_findings(config: dict[str, Any]) -> list[str]:
    findings: list[str] = []
    servers = config.get("mcpServers")
    if not isinstance(servers, dict) or not servers:
        return ["missing_mcp_servers"]
    for name, server in servers.items():
        if not isinstance(server, dict):
            findings.append(f"{name}:invalid_server")
            continue
        if "allowedTools" in server or "allowTools" in server:
            findings.append(f"{name}:legacy_allowlist")
        note = str(server.get("note") or "")
        if "full telegram-mcp tool surface" not in note:
            findings.append(f"{name}:missing_full_surface_note")
    return findings
