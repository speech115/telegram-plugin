"""Tool registration entrypoint."""

from .chat_tools import (
    get_chat_info,
    list_chats,
    register as register_chat_tools,
    resolve_username,
    search_public_chats,
)
from .contact_tools import (
    add_contact,
    delete_contact,
    get_blocked_users,
    import_contacts,
    list_contacts,
    register as register_contact_tools,
    search_contacts,
    set_user_blocked,
)
from .dialog_facade_tools import (
    collect_context,
    collect_dialog_context,
    draft_reply,
    find_dialog,
    prepare_reply_message,
    prepare_send_message,
    prepare_dialog_reply,
    read_dialog,
    read_dialog_by_date,
    read_recent_dialog,
    read_today_dialog,
    register as register_dialog_facade_tools,
    reply_in_dialog,
    reply_message,
    resolve_dialog,
    search_dialog_messages,
    send_dialog_message,
)
from .group_tools import (
    create_channel,
    create_group,
    delete_chat_photo,
    demote_admin,
    edit_chat_title,
    get_invite_link,
    get_participants,
    invite_to_group,
    leave_chat,
    promote_admin,
    register as register_group_tools,
    set_user_banned,
)
from .media_tools import (
    download_dialog_media,
    download_media,
    download_media_batch,
    download_story_media,
    prepare_media_inspection_manifest,
    register as register_media_tools,
    register_facade as register_media_facade_tools,
    send_file,
)
from .message_tools import (
    create_poll,
    delete_messages,
    edit_message,
    forward_messages,
    get_message_link,
    get_pinned_messages,
    list_messages,
    mark_as_read,
    read_dialog_slice,
    register as register_message_tools,
    reply_to_message,
    search_messages,
    send_message,
    send_message_with_buttons,
    send_reaction,
    send_voice,
    set_message_pinned,
    transcribe_voice,
)
from .privacy_tools import (
    register as register_privacy_tools,
    set_chat_archived,
    set_chat_muted,
)
from .profile_tools import (
    delete_profile_photo,
    get_user_photos,
    get_user_status,
    register as register_profile_tools,
    update_profile,
)
from .story_tools import (
    export_story_link,
    get_peer_stories,
    get_pinned_stories,
    get_stories_archive,
    get_stories_by_id,
    get_story_viewers,
    get_story_views,
    register as register_story_tools,
)
from .user_tools import (
    doctor_check,
    get_me,
    health_check,
    register as register_user_tools,
)

FACADE_TOOL_NAMES = {
    "doctor_check",
    "get_me",
    "collect_context",
    "collect_dialog_context",
    "draft_reply",
    "download_dialog_media",
    "download_media",
    "download_media_batch",
    "find_dialog",
    "prepare_dialog_reply",
    "prepare_media_inspection_manifest",
    "prepare_reply_message",
    "prepare_send_message",
    "read_dialog",
    "read_dialog_by_date",
    "read_recent_dialog",
    "read_today_dialog",
    "resolve_dialog",
    "search_dialog_messages",
    "transcribe_voice",
}

FULL_TOOL_PROFILES = {"all", "full", "admin", "legacy"}


def register_all_tools(mcp, *, profile: str | None = None) -> None:
    from os import getenv

    selected_profile = (profile or getenv("TELEGRAM_MCP_TOOL_PROFILE", "facade")).strip().lower()
    if selected_profile not in FULL_TOOL_PROFILES:
        register_user_tools(mcp)
        register_dialog_facade_tools(mcp)
        register_media_facade_tools(mcp)
        register_message_tools(mcp, facade_only=True)
        return

    register_user_tools(mcp)
    register_chat_tools(mcp)
    register_group_tools(mcp)
    register_message_tools(mcp)
    register_dialog_facade_tools(mcp, include_writes=True)
    register_contact_tools(mcp)
    register_media_tools(mcp)
    register_story_tools(mcp)
    register_profile_tools(mcp)
    register_privacy_tools(mcp)
