import unittest
from types import SimpleNamespace

from telegram_mcp.download_post import (
    ParsedLink,
    _ext_from_message,
    _parse_threshold_mb,
    _telethon_media_kind,
    _telethon_media_size_bytes,
    parse_post_link,
)
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


class TelethonMediaKindTests(unittest.TestCase):
    def test_photo_is_photo_kind(self):
        msg = SimpleNamespace(media=SimpleNamespace(document=None, photo=object()))
        self.assertEqual(_telethon_media_kind(msg), "photo")

    def test_video_mime_is_video_kind(self):
        doc = SimpleNamespace(attributes=[], mime_type="video/mp4", size=123)
        msg = SimpleNamespace(media=SimpleNamespace(document=doc, photo=None))
        self.assertEqual(_telethon_media_kind(msg), "video")

    def test_audio_mime_is_audio_kind(self):
        doc = SimpleNamespace(attributes=[], mime_type="audio/mpeg", size=123)
        msg = SimpleNamespace(media=SimpleNamespace(document=doc, photo=None))
        self.assertEqual(_telethon_media_kind(msg), "audio")

    def test_other_document_mime_is_document_kind(self):
        doc = SimpleNamespace(attributes=[], mime_type="application/pdf", size=123)
        msg = SimpleNamespace(media=SimpleNamespace(document=doc, photo=None))
        self.assertEqual(_telethon_media_kind(msg), "document")

    def test_no_media_is_unsupported(self):
        msg = SimpleNamespace(media=None)
        self.assertIsNone(_telethon_media_kind(msg))


class TelethonMediaSizeBytesTests(unittest.TestCase):
    def test_document_size(self):
        doc = SimpleNamespace(size=123456)
        msg = SimpleNamespace(media=SimpleNamespace(document=doc, photo=None))
        self.assertEqual(_telethon_media_size_bytes(msg), 123456)

    def test_photo_largest_size(self):
        sizes = [SimpleNamespace(size=100), SimpleNamespace(size=9000)]
        photo = SimpleNamespace(sizes=sizes)
        msg = SimpleNamespace(media=SimpleNamespace(document=None, photo=photo))
        self.assertEqual(_telethon_media_size_bytes(msg), 9000)

    def test_no_media_is_none(self):
        msg = SimpleNamespace(media=None)
        self.assertIsNone(_telethon_media_size_bytes(msg))


class ParseThresholdMbTests(unittest.TestCase):
    def test_valid_value(self):
        self.assertEqual(_parse_threshold_mb("50"), 50.0)

    def test_none_falls_back_to_default(self):
        self.assertEqual(_parse_threshold_mb(None), 20.0)

    def test_garbage_falls_back_to_default_instead_of_raising(self):
        self.assertEqual(_parse_threshold_mb("twenty"), 20.0)

    def test_empty_falls_back_to_default(self):
        self.assertEqual(_parse_threshold_mb(""), 20.0)


if __name__ == "__main__":
    unittest.main()
