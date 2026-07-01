import os
import unittest
from unittest.mock import patch

from mcp.server.fastmcp import FastMCP

from telegram_mcp.metadata_tools_spec import METADATA_TOOL_NAMES
from telegram_mcp.tools import FACADE_TOOL_NAMES, register_all_tools


class RegistrationTests(unittest.TestCase):
    def test_default_tool_registration_is_full_surface(self):
        mcp = FastMCP("test")
        with patch.dict(os.environ, {}, clear=True):
            register_all_tools(mcp)
        names = {tool.name for tool in mcp._tool_manager.list_tools()}

        self.assertGreater(len(names), len(FACADE_TOOL_NAMES))
        self.assertIn("create_channel", names)
        self.assertIn("delete_messages", names)
        self.assertIn("read_today_dialog", names)
        self.assertIn("prepare_dialog_reply", names)
        self.assertIn("draft_reply", names)
        self.assertIn("search_dialog_messages", names)
        self.assertIn("telegram_send", names)

    def test_facade_profile_remains_available_when_explicit(self):
        mcp = FastMCP("test")
        register_all_tools(mcp, profile="facade")
        names = {tool.name for tool in mcp._tool_manager.list_tools()}

        self.assertEqual(names, FACADE_TOOL_NAMES)
        self.assertNotIn("create_channel", names)
        self.assertNotIn("delete_messages", names)
        self.assertNotIn("telegram_export_members", names)
        self.assertNotIn("send_file", names)

    def test_full_tool_registration_surface_is_stable(self):
        mcp = FastMCP("test")
        register_all_tools(mcp, profile="full")
        names = [tool.name for tool in mcp._tool_manager.list_tools()]

        expected = [
                # User & health
                "get_me",
                "doctor_check",
                # Chat
                "list_chats",
                "get_chat_info",
                "resolve_username",
                "search_public_chats",
                # Group management
                "create_group",
                "create_channel",
                "edit_chat_title",
                "delete_chat_photo",
                "leave_chat",
                "get_participants",
                "promote_admin",
                "demote_admin",
                "set_user_banned",
                "get_invite_link",
                "invite_to_group",
                # Messages
                "list_messages",
                "read_dialog_slice",
                "search_messages",
                "global_search",
                "sent_media_search",
                "send_message",
                "reply_to_message",
                "edit_message",
                "delete_messages",
                "forward_messages",
                "set_message_pinned",
                "transcribe_voice",
                "send_reaction",
                "mark_as_read",
                "get_message_link",
                "create_poll",
                "get_pinned_messages",
                "send_voice",
                "send_message_with_buttons",
                # Dialog facade
                "resolve_dialog",
                "find_dialog",
                "read_dialog_by_date",
                "read_today_dialog",
                "read_recent_dialog",
                "read_dialog",
                "collect_dialog_context",
                "collect_context",
                "prepare_dialog_reply",
                "draft_reply",
                "prepare_send_message",
                "prepare_reply_message",
                "search_dialog_messages",
                "telegram_read",
                "telegram_search",
                "telegram_prepare_reply",
                "send_dialog_message",
                "telegram_send",
                "reply_in_dialog",
                "reply_message",
                "telegram_confirmed_send",
                "telegram_export_members",
                *METADATA_TOOL_NAMES,
                # Contacts
                "list_contacts",
                "search_contacts",
                "add_contact",
                "delete_contact",
                "set_user_blocked",
                "get_blocked_users",
                "import_contacts",
                # Media
                "download_media",
                "download_media_batch",
                "download_dialog_media",
                "prepare_media_inspection_manifest",
                "telegram_inspect_media",
                "download_story_media",
                "send_file",
                # Stories
                "get_peer_stories",
                "get_stories_by_id",
                "get_pinned_stories",
                "get_stories_archive",
                "get_story_views",
                "get_story_viewers",
                "export_story_link",
                # Threads/forums
                "list_forum_topics",
                "get_forum_topics_by_id",
                "get_discussion_message",
                "get_thread_replies",
                # Reactions
                "get_message_reactions",
                "get_unread_reactions",
                # Profile
                "update_profile",
                "delete_profile_photo",
                "get_user_photos",
                "get_user_status",
                # Privacy & settings
                "set_chat_muted",
                "set_chat_archived",
        ]

        self.assertEqual(len(names), len(expected))
        self.assertEqual(set(names), set(expected))

    def test_invite_link_is_not_registered_as_read_only(self):
        mcp = FastMCP("test")
        register_all_tools(mcp, profile="full")
        tools = {tool.name: tool for tool in mcp._tool_manager.list_tools()}

        self.assertFalse(tools["get_invite_link"].annotations.readOnlyHint)

    def test_member_export_is_owner_full_only_and_not_read_only(self):
        facade = FastMCP("facade")
        register_all_tools(facade, profile="facade")
        facade_tools = {tool.name: tool for tool in facade._tool_manager.list_tools()}
        self.assertNotIn("telegram_export_members", facade_tools)

        full = FastMCP("full")
        register_all_tools(full, profile="full")
        full_tools = {tool.name: tool for tool in full._tool_manager.list_tools()}
        self.assertFalse(full_tools["telegram_export_members"].annotations.readOnlyHint)

    def test_unknown_profile_value_raises_instead_of_silently_granting_full_surface(self):
        mcp = FastMCP("test")
        with self.assertRaises(ValueError):
            register_all_tools(mcp, profile="facde")

    def test_unknown_profile_value_from_env_raises_instead_of_silently_granting_full_surface(self):
        mcp = FastMCP("test")
        with patch.dict(os.environ, {"TELEGRAM_MCP_TOOL_PROFILE": "readonly"}, clear=True):
            with self.assertRaises(ValueError):
                register_all_tools(mcp)

    def test_unset_env_still_defaults_to_full_surface(self):
        mcp = FastMCP("test")
        with patch.dict(os.environ, {}, clear=True):
            register_all_tools(mcp)
        names = {tool.name for tool in mcp._tool_manager.list_tools()}

        self.assertIn("create_channel", names)
