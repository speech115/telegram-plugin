import unittest
from types import SimpleNamespace

from telegram_mcp.download_post import ParsedLink, _ext_from_message, parse_post_link
from telegram_mcp.mcp_http_client import McpCliError


class ParsePostLinkTests(unittest.TestCase):
    def test_parses_private_channel_link(self):
        parsed = parse_post_link("https://t.me/c/1234567890/42")

        self.assertEqual(parsed, ParsedLink(chat=-1001234567890, message_id=42, label="c1234567890"))

    def test_parses_private_channel_link_without_scheme(self):
        parsed = parse_post_link("t.me/c/1234567890/42")

        self.assertEqual(parsed.chat, -1001234567890)
        self.assertEqual(parsed.message_id, 42)

    def test_parses_private_channel_link_with_thread_id(self):
        parsed = parse_post_link("https://t.me/c/1234567890/7/42")

        self.assertEqual(parsed.chat, -1001234567890)
        self.assertEqual(parsed.message_id, 42)

    def test_parses_public_username_link(self):
        parsed = parse_post_link("https://t.me/sral_v_nastav/99")

        self.assertEqual(parsed, ParsedLink(chat="@sral_v_nastav", message_id=99, label="sral_v_nastav"))

    def test_parses_public_username_link_with_thread_id(self):
        parsed = parse_post_link("t.me/sral_v_nastav/7/99")

        self.assertEqual(parsed.chat, "@sral_v_nastav")
        self.assertEqual(parsed.message_id, 99)

    def test_rejects_non_post_link(self):
        with self.assertRaises(McpCliError):
            parse_post_link("https://example.com/not-a-telegram-link")


class ExtFromMessageTests(unittest.TestCase):
    def test_uses_file_name_extension_when_present(self):
        attr = SimpleNamespace(file_name="clip.mov")
        doc = SimpleNamespace(attributes=[attr], mime_type="video/quicktime")
        msg = SimpleNamespace(media=SimpleNamespace(document=doc, photo=None))

        self.assertEqual(_ext_from_message(msg), ".mov")

    def test_falls_back_to_mp4_for_video_mime(self):
        doc = SimpleNamespace(attributes=[], mime_type="video/mp4")
        msg = SimpleNamespace(media=SimpleNamespace(document=doc, photo=None))

        self.assertEqual(_ext_from_message(msg), ".mp4")

    def test_falls_back_to_generic_mime_subtype(self):
        doc = SimpleNamespace(attributes=[], mime_type="application/pdf")
        msg = SimpleNamespace(media=SimpleNamespace(document=doc, photo=None))

        self.assertEqual(_ext_from_message(msg), ".pdf")

    def test_uses_jpg_for_photo(self):
        msg = SimpleNamespace(media=SimpleNamespace(document=None, photo=object()))

        self.assertEqual(_ext_from_message(msg), ".jpg")

    def test_falls_back_to_bin_when_no_media(self):
        msg = SimpleNamespace(media=None)

        self.assertEqual(_ext_from_message(msg), ".bin")


if __name__ == "__main__":
    unittest.main()
