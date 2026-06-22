import unittest

from telethon.tl import alltlobjects, types

from telegram_mcp.telethon_compat import (
    CURRENT_CONSTRUCTOR_ALIASES,
    CHANNEL_COMPAT_SCHEMA_VERSION,
    USER_COMPAT_SCHEMA_VERSION,
    apply_telethon_compat,
    telethon_compat_status,
)
from telegram_mcp.utils import resolve_entity


class TelethonCompatTest(unittest.TestCase):
    def test_current_constructor_aliases_are_registered(self):
        original = {
            constructor_id: alltlobjects.tlobjects.pop(constructor_id, None)
            for constructor_id in CURRENT_CONSTRUCTOR_ALIASES
        }
        try:
            apply_telethon_compat()
            for constructor_id, class_name in CURRENT_CONSTRUCTOR_ALIASES.items():
                self.assertIs(alltlobjects.tlobjects[constructor_id], getattr(types, class_name))
        finally:
            for constructor_id, value in original.items():
                if value is not None:
                    alltlobjects.tlobjects[constructor_id] = value

    def test_channel_stories_max_id_reads_current_int_schema(self):
        class Reader:
            ints = [0, 16, 123]

            def read_int(self):
                return self.ints.pop(0)

            def read_long(self):
                return 456

            def tgread_string(self):
                return "channel"

            def tgread_object(self):
                return None

            def tgread_date(self):
                return None

        apply_telethon_compat()

        channel = types.Channel.from_reader(Reader())

        self.assertEqual(channel.stories_max_id, 123)

    def test_user_stories_max_id_reads_current_int_schema(self):
        class Reader:
            ints = [0, 32, 777]

            def read_int(self):
                return self.ints.pop(0)

            def read_long(self):
                return 456

            def tgread_string(self):
                return "user"

            def tgread_object(self):
                raise AssertionError("stories_max_id must be read as int")

        apply_telethon_compat()

        user = types.User.from_reader(Reader())

        self.assertEqual(user.stories_max_id, 777)

    def test_user_peer_colors_accept_compact_int_schema(self):
        class Reader:
            ints = [0, 32 | 256 | 512, 777, 2, 795]
            position = 0

            def read_int(self, signed=True):
                value = self.ints[self.position]
                self.position += 1
                return value

            def read_long(self):
                return 456

            def tgread_string(self):
                return "user"

            def tgread_object(self):
                raise AssertionError("compact peer colors must be read as int")

            def tell_position(self):
                return self.position

            def set_position(self, position):
                self.position = position

        apply_telethon_compat()

        user = types.User.from_reader(Reader())

        self.assertEqual(user.stories_max_id, 777)
        self.assertEqual(user.color, 2)
        self.assertEqual(user.profile_color, 795)

    def test_user_peer_colors_normalize_object_schema_to_color_id(self):
        class Reader:
            ints = [0, 32 | 256, 777, types.PeerColor.CONSTRUCTOR_ID, 1, 9]
            position = 0

            def read_int(self, signed=True):
                value = self.ints[self.position]
                self.position += 1
                return value

            def read_long(self):
                return 456

            def tgread_string(self):
                return "user"

            def tgread_object(self):
                constructor_id = self.read_int(signed=False)
                if constructor_id != types.PeerColor.CONSTRUCTOR_ID:
                    raise AssertionError(f"unexpected constructor {constructor_id!r}")
                return types.PeerColor.from_reader(self)

            def tell_position(self):
                return self.position

            def set_position(self, position):
                self.position = position

        apply_telethon_compat()

        user = types.User.from_reader(Reader())

        self.assertEqual(user.stories_max_id, 777)
        self.assertEqual(user.color, 9)

    def test_user_parser_consumes_trailing_peer_color_object(self):
        class Reader:
            ints = [0, 32 | 256, 777, 795, types.PeerColor.CONSTRUCTOR_ID, 1, 9]
            position = 0

            def read_int(self, signed=True):
                value = self.ints[self.position]
                self.position += 1
                return value

            def read_long(self):
                return 456

            def tgread_string(self):
                return "user"

            def tgread_object(self):
                constructor_id = self.read_int(signed=False)
                if constructor_id != types.PeerColor.CONSTRUCTOR_ID:
                    raise AssertionError(f"unexpected constructor {constructor_id!r}")
                return types.PeerColor.from_reader(self)

            def tell_position(self):
                return self.position

            def set_position(self, position):
                self.position = position

        reader = Reader()
        apply_telethon_compat()

        user = types.User.from_reader(reader)

        self.assertEqual(user.stories_max_id, 777)
        self.assertEqual(user.color, 795)
        self.assertEqual(user.profile_color, 9)
        self.assertEqual(reader.position, len(reader.ints))

    def test_resolve_entity_reapplies_compat_before_get_entity(self):
        original_reader = types.Channel.from_reader
        original_flag = getattr(types.Channel, "_telegram_mcp_current_schema_patch", None)

        async def run():
            class Client:
                async def get_entity(self, chat):
                    self.saw_patched = getattr(types.Channel, "_telegram_mcp_current_schema_patch", False)
                    self.reader_module = types.Channel.from_reader.__func__.__module__
                    return chat

            client = Client()
            result = await resolve_entity(client, "@example")
            return result, client

        try:
            if hasattr(types.Channel, "_telegram_mcp_current_schema_patch"):
                delattr(types.Channel, "_telegram_mcp_current_schema_patch")
            types.Channel.from_reader = classmethod(lambda cls, reader: None)

            result, client = __import__("asyncio").run(run())

            self.assertEqual(result, "@example")
            self.assertTrue(client.saw_patched)
            self.assertEqual(client.reader_module, "telegram_mcp.telethon_compat")
        finally:
            types.Channel.from_reader = original_reader
            if original_flag is None:
                if hasattr(types.Channel, "_telegram_mcp_current_schema_patch"):
                    delattr(types.Channel, "_telegram_mcp_current_schema_patch")
            else:
                types.Channel._telegram_mcp_current_schema_patch = original_flag

    def test_telethon_compat_status_reports_runtime_contract(self):
        apply_telethon_compat()

        status = telethon_compat_status()

        self.assertTrue(status["ok"])
        self.assertTrue(status["channel_from_reader_patched"])
        self.assertEqual(status["channel_from_reader_patch_version"], CHANNEL_COMPAT_SCHEMA_VERSION)
        self.assertEqual(status["channel_from_reader_module"], "telegram_mcp.telethon_compat")
        self.assertTrue(status["user_from_reader_patched"])
        self.assertEqual(status["user_from_reader_patch_version"], USER_COMPAT_SCHEMA_VERSION)
        self.assertEqual(status["user_from_reader_module"], "telegram_mcp.telethon_compat")
        self.assertTrue(status["constructor_aliases_ok"])

    def test_apply_telethon_compat_replaces_stale_channel_patch_version(self):
        original_reader = types.Channel.from_reader
        original_flag = getattr(types.Channel, "_telegram_mcp_current_schema_patch", None)
        original_version = getattr(types.Channel, "_telegram_mcp_current_schema_patch_version", None)
        try:
            types.Channel.from_reader = classmethod(lambda cls, reader: None)
            types.Channel._telegram_mcp_current_schema_patch = True
            types.Channel._telegram_mcp_current_schema_patch_version = CHANNEL_COMPAT_SCHEMA_VERSION - 1

            apply_telethon_compat()

            self.assertEqual(types.Channel.from_reader.__func__.__module__, "telegram_mcp.telethon_compat")
            self.assertEqual(types.Channel._telegram_mcp_current_schema_patch_version, CHANNEL_COMPAT_SCHEMA_VERSION)
        finally:
            types.Channel.from_reader = original_reader
            if original_flag is None:
                if hasattr(types.Channel, "_telegram_mcp_current_schema_patch"):
                    delattr(types.Channel, "_telegram_mcp_current_schema_patch")
            else:
                types.Channel._telegram_mcp_current_schema_patch = original_flag
            if original_version is None:
                if hasattr(types.Channel, "_telegram_mcp_current_schema_patch_version"):
                    delattr(types.Channel, "_telegram_mcp_current_schema_patch_version")
            else:
                types.Channel._telegram_mcp_current_schema_patch_version = original_version

    def test_apply_telethon_compat_replaces_stale_user_patch_version(self):
        original_reader = types.User.from_reader
        original_flag = getattr(types.User, "_telegram_mcp_current_schema_patch", None)
        original_version = getattr(types.User, "_telegram_mcp_current_schema_patch_version", None)
        try:
            types.User.from_reader = classmethod(lambda cls, reader: None)
            types.User._telegram_mcp_current_schema_patch = True
            types.User._telegram_mcp_current_schema_patch_version = USER_COMPAT_SCHEMA_VERSION - 1

            apply_telethon_compat()

            self.assertEqual(types.User.from_reader.__func__.__module__, "telegram_mcp.telethon_compat")
            self.assertEqual(types.User._telegram_mcp_current_schema_patch_version, USER_COMPAT_SCHEMA_VERSION)
        finally:
            types.User.from_reader = original_reader
            if original_flag is None:
                if hasattr(types.User, "_telegram_mcp_current_schema_patch"):
                    delattr(types.User, "_telegram_mcp_current_schema_patch")
            else:
                types.User._telegram_mcp_current_schema_patch = original_flag
            if original_version is None:
                if hasattr(types.User, "_telegram_mcp_current_schema_patch_version"):
                    delattr(types.User, "_telegram_mcp_current_schema_patch_version")
            else:
                types.User._telegram_mcp_current_schema_patch_version = original_version


if __name__ == "__main__":
    unittest.main()
