"""Runtime compatibility shims for Telegram schema drift in Telethon."""

from __future__ import annotations


CURRENT_CONSTRUCTOR_ALIASES = {
    0x6917560B: "MessageReplyHeader",
    0xFE685355: "Channel",
    0x9815CEC8: "Message",
    0x695150D7: "MessageMediaPhoto",
    0x020B1422: "User",
    0xACA1657B: "UpdateMessagePoll",
    0xEDF164F1: "StoryItem",
}

CURRENT_MESSAGE_CONSTRUCTOR_ID = 0x9815CEC8
CHANNEL_COMPAT_SCHEMA_VERSION = 2
USER_COMPAT_SCHEMA_VERSION = 3
PEER_COLOR_CONSTRUCTOR_ID = 0xB54B5ACF


def apply_telethon_compat() -> None:
    """Register constructor aliases Telegram may emit before Telethon republishes."""

    from telethon.tl import alltlobjects, types

    for constructor_id, class_name in CURRENT_CONSTRUCTOR_ALIASES.items():
        alltlobjects.tlobjects.setdefault(constructor_id, getattr(types, class_name))
    _patch_channel_from_reader(types.Channel)
    _patch_user_from_reader(types.User)


def telethon_compat_status() -> dict[str, object]:
    """Return runtime-owned evidence that Telethon compatibility shims are active."""

    from telethon.tl import alltlobjects, types

    alias_results = {
        hex(constructor_id): alltlobjects.tlobjects.get(constructor_id) is getattr(types, class_name)
        for constructor_id, class_name in CURRENT_CONSTRUCTOR_ALIASES.items()
    }
    payload: dict[str, object] = {
        "channel_from_reader_patched": getattr(types.Channel, "_telegram_mcp_current_schema_patch", False),
        "channel_from_reader_patch_version": getattr(types.Channel, "_telegram_mcp_current_schema_patch_version", None),
        "channel_from_reader_module": types.Channel.from_reader.__func__.__module__,
        "user_from_reader_patched": getattr(types.User, "_telegram_mcp_current_schema_patch", False),
        "user_from_reader_patch_version": getattr(types.User, "_telegram_mcp_current_schema_patch_version", None),
        "user_from_reader_module": types.User.from_reader.__func__.__module__,
        "constructor_aliases": alias_results,
        "constructor_aliases_ok": all(alias_results.values()),
    }
    payload["ok"] = (
        payload["channel_from_reader_patched"] is True
        and payload["channel_from_reader_patch_version"] == CHANNEL_COMPAT_SCHEMA_VERSION
        and payload["channel_from_reader_module"] == "telegram_mcp.telethon_compat"
        and payload["user_from_reader_patched"] is True
        and payload["user_from_reader_patch_version"] == USER_COMPAT_SCHEMA_VERSION
        and payload["user_from_reader_module"] == "telegram_mcp.telethon_compat"
        and payload["constructor_aliases_ok"] is True
    )
    return payload


def _patch_channel_from_reader(channel_cls: type) -> None:
    if (
        getattr(channel_cls, "_telegram_mcp_current_schema_patch", False)
        and getattr(channel_cls, "_telegram_mcp_current_schema_patch_version", None) == CHANNEL_COMPAT_SCHEMA_VERSION
    ):
        return

    def from_reader(cls, reader):
        flags = reader.read_int()

        _creator = bool(flags & 1)
        _left = bool(flags & 4)
        _broadcast = bool(flags & 32)
        _verified = bool(flags & 128)
        _megagroup = bool(flags & 256)
        _restricted = bool(flags & 512)
        _signatures = bool(flags & 2048)
        _min = bool(flags & 4096)
        _scam = bool(flags & 524288)
        _has_link = bool(flags & 1048576)
        _has_geo = bool(flags & 2097152)
        _slowmode_enabled = bool(flags & 4194304)
        _call_active = bool(flags & 8388608)
        _call_not_empty = bool(flags & 16777216)
        _fake = bool(flags & 33554432)
        _gigagroup = bool(flags & 67108864)
        _noforwards = bool(flags & 134217728)
        _join_to_send = bool(flags & 268435456)
        _join_request = bool(flags & 536870912)
        _forum = bool(flags & 1073741824)
        flags2 = reader.read_int()

        _stories_hidden = bool(flags2 & 2)
        _stories_hidden_min = bool(flags2 & 4)
        _stories_unavailable = bool(flags2 & 8)
        _signature_profiles = bool(flags2 & 4096)
        _autotranslation = bool(flags2 & 32768)
        _broadcast_messages_allowed = bool(flags2 & 65536)
        _monoforum = bool(flags2 & 131072)
        _forum_tabs = bool(flags2 & 524288)
        _id = reader.read_long()
        _access_hash = reader.read_long() if flags & 8192 else None
        _title = reader.tgread_string()
        _username = reader.tgread_string() if flags & 64 else None
        _photo = reader.tgread_object()
        _date = reader.tgread_date()
        if flags & 512:
            reader.read_int()
            _restriction_reason = [reader.tgread_object() for _ in range(reader.read_int())]
        else:
            _restriction_reason = None
        _admin_rights = reader.tgread_object() if flags & 16384 else None
        _banned_rights = reader.tgread_object() if flags & 32768 else None
        _default_banned_rights = reader.tgread_object() if flags & 262144 else None
        _participants_count = reader.read_int() if flags & 131072 else None
        if flags2 & 1:
            reader.read_int()
            _usernames = [reader.tgread_object() for _ in range(reader.read_int())]
        else:
            _usernames = None
        _stories_max_id = reader.read_int() if flags2 & 16 else None
        _color = reader.tgread_object() if flags2 & 128 else None
        _profile_color = reader.tgread_object() if flags2 & 256 else None
        _emoji_status = reader.tgread_object() if flags2 & 512 else None
        _level = reader.read_int() if flags2 & 1024 else None
        _subscription_until_date = reader.tgread_date() if flags2 & 2048 else None
        _bot_verification_icon = reader.read_long() if flags2 & 8192 else None
        _send_paid_messages_stars = reader.read_long() if flags2 & 16384 else None
        _linked_monoforum_id = reader.read_long() if flags2 & 262144 else None
        return cls(
            id=_id,
            title=_title,
            photo=_photo,
            date=_date,
            creator=_creator,
            left=_left,
            broadcast=_broadcast,
            verified=_verified,
            megagroup=_megagroup,
            restricted=_restricted,
            signatures=_signatures,
            min=_min,
            scam=_scam,
            has_link=_has_link,
            has_geo=_has_geo,
            slowmode_enabled=_slowmode_enabled,
            call_active=_call_active,
            call_not_empty=_call_not_empty,
            fake=_fake,
            gigagroup=_gigagroup,
            noforwards=_noforwards,
            join_to_send=_join_to_send,
            join_request=_join_request,
            forum=_forum,
            stories_hidden=_stories_hidden,
            stories_hidden_min=_stories_hidden_min,
            stories_unavailable=_stories_unavailable,
            signature_profiles=_signature_profiles,
            autotranslation=_autotranslation,
            broadcast_messages_allowed=_broadcast_messages_allowed,
            monoforum=_monoforum,
            forum_tabs=_forum_tabs,
            access_hash=_access_hash,
            username=_username,
            restriction_reason=_restriction_reason,
            admin_rights=_admin_rights,
            banned_rights=_banned_rights,
            default_banned_rights=_default_banned_rights,
            participants_count=_participants_count,
            usernames=_usernames,
            stories_max_id=_stories_max_id,
            color=_color,
            profile_color=_profile_color,
            emoji_status=_emoji_status,
            level=_level,
            subscription_until_date=_subscription_until_date,
            bot_verification_icon=_bot_verification_icon,
            send_paid_messages_stars=_send_paid_messages_stars,
            linked_monoforum_id=_linked_monoforum_id,
        )

    channel_cls.from_reader = classmethod(from_reader)
    channel_cls._telegram_mcp_current_schema_patch = True
    channel_cls._telegram_mcp_current_schema_patch_version = CHANNEL_COMPAT_SCHEMA_VERSION


def _patch_user_from_reader(user_cls: type) -> None:
    if (
        getattr(user_cls, "_telegram_mcp_current_schema_patch", False)
        and getattr(user_cls, "_telegram_mcp_current_schema_patch_version", None) == USER_COMPAT_SCHEMA_VERSION
    ):
        return

    def from_reader(cls, reader):
        flags = reader.read_int()

        _is_self = bool(flags & 1024)
        _contact = bool(flags & 2048)
        _mutual_contact = bool(flags & 4096)
        _deleted = bool(flags & 8192)
        _bot = bool(flags & 16384)
        _bot_chat_history = bool(flags & 32768)
        _bot_nochats = bool(flags & 65536)
        _verified = bool(flags & 131072)
        _restricted = bool(flags & 262144)
        _min = bool(flags & 1048576)
        _bot_inline_geo = bool(flags & 2097152)
        _support = bool(flags & 8388608)
        _scam = bool(flags & 16777216)
        _apply_min_photo = bool(flags & 33554432)
        _fake = bool(flags & 67108864)
        _bot_attach_menu = bool(flags & 134217728)
        _premium = bool(flags & 268435456)
        _attach_menu_enabled = bool(flags & 536870912)
        flags2 = reader.read_int()

        _bot_can_edit = bool(flags2 & 2)
        _close_friend = bool(flags2 & 4)
        _stories_hidden = bool(flags2 & 8)
        _stories_unavailable = bool(flags2 & 16)
        _contact_require_premium = bool(flags2 & 1024)
        _bot_business = bool(flags2 & 2048)
        _bot_has_main_app = bool(flags2 & 8192)
        _bot_forum_view = bool(flags2 & 65536)
        _bot_forum_can_manage_topics = bool(flags2 & 131072)
        _bot_can_manage_bots = bool(flags2 & 262144)
        _bot_guestchat = bool(flags2 & 524288)
        _bot_guard = bool(flags2 & 1048576)
        _id = reader.read_long()
        _access_hash = reader.read_long() if flags & 1 else None
        _first_name = reader.tgread_string() if flags & 2 else None
        _last_name = reader.tgread_string() if flags & 4 else None
        _username = reader.tgread_string() if flags & 8 else None
        _phone = reader.tgread_string() if flags & 16 else None
        _photo = reader.tgread_object() if flags & 32 else None
        _status = reader.tgread_object() if flags & 64 else None
        _bot_info_version = reader.read_int() if flags & 16384 else None
        if flags & 262144:
            reader.read_int()
            _restriction_reason = [reader.tgread_object() for _ in range(reader.read_int())]
        else:
            _restriction_reason = None
        _bot_inline_placeholder = reader.tgread_string() if flags & 524288 else None
        _lang_code = reader.tgread_string() if flags & 4194304 else None
        _emoji_status = reader.tgread_object() if flags & 1073741824 else None
        if flags2 & 1:
            reader.read_int()
            _usernames = [reader.tgread_object() for _ in range(reader.read_int())]
        else:
            _usernames = None
        _stories_max_id = reader.read_int() if flags2 & 32 else None
        _color = _read_peer_color_compat(reader) if flags2 & 256 else None
        _profile_color = _read_peer_color_compat(reader) if flags2 & 512 else None
        _bot_active_users = reader.read_int() if flags2 & 4096 else None
        _bot_verification_icon = reader.read_long() if flags2 & 16384 else None
        _send_paid_messages_stars = reader.read_long() if flags2 & 32768 else None
        if _profile_color is None and _peek_constructor_id(reader) == PEER_COLOR_CONSTRUCTOR_ID:
            _profile_color = _read_peer_color_compat(reader)
        while _peek_constructor_id(reader) == PEER_COLOR_CONSTRUCTOR_ID:
            _read_peer_color_compat(reader)
        return cls(
            id=_id,
            is_self=_is_self,
            contact=_contact,
            mutual_contact=_mutual_contact,
            deleted=_deleted,
            bot=_bot,
            bot_chat_history=_bot_chat_history,
            bot_nochats=_bot_nochats,
            verified=_verified,
            restricted=_restricted,
            min=_min,
            bot_inline_geo=_bot_inline_geo,
            support=_support,
            scam=_scam,
            apply_min_photo=_apply_min_photo,
            fake=_fake,
            bot_attach_menu=_bot_attach_menu,
            premium=_premium,
            attach_menu_enabled=_attach_menu_enabled,
            bot_can_edit=_bot_can_edit,
            close_friend=_close_friend,
            stories_hidden=_stories_hidden,
            stories_unavailable=_stories_unavailable,
            contact_require_premium=_contact_require_premium,
            bot_business=_bot_business,
            bot_has_main_app=_bot_has_main_app,
            bot_forum_view=_bot_forum_view,
            bot_forum_can_manage_topics=_bot_forum_can_manage_topics,
            bot_can_manage_bots=_bot_can_manage_bots,
            bot_guestchat=_bot_guestchat,
            bot_guard=_bot_guard,
            access_hash=_access_hash,
            first_name=_first_name,
            last_name=_last_name,
            username=_username,
            phone=_phone,
            photo=_photo,
            status=_status,
            bot_info_version=_bot_info_version,
            restriction_reason=_restriction_reason,
            bot_inline_placeholder=_bot_inline_placeholder,
            lang_code=_lang_code,
            emoji_status=_emoji_status,
            usernames=_usernames,
            stories_max_id=_stories_max_id,
            color=_color,
            profile_color=_profile_color,
            bot_active_users=_bot_active_users,
            bot_verification_icon=_bot_verification_icon,
            send_paid_messages_stars=_send_paid_messages_stars,
        )

    user_cls.from_reader = classmethod(from_reader)
    user_cls._telegram_mcp_current_schema_patch = True
    user_cls._telegram_mcp_current_schema_patch_version = USER_COMPAT_SCHEMA_VERSION


def _read_peer_color_compat(reader):
    constructor_id = _peek_constructor_id(reader)
    if constructor_id == PEER_COLOR_CONSTRUCTOR_ID:
        peer_color = reader.tgread_object()
        return getattr(peer_color, "color", None)
    return reader.read_int()


def _peek_constructor_id(reader):
    if not hasattr(reader, "tell_position") or not hasattr(reader, "set_position"):
        return None
    position = reader.tell_position()
    try:
        return reader.read_int(signed=False)
    except Exception:
        return None
    finally:
        reader.set_position(position)
