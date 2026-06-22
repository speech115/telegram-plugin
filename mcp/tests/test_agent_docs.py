import unittest

from telegram_mcp.agent_docs import load_doc_topic, list_doc_topics


class AgentDocTests(unittest.TestCase):
    def test_list_doc_topics_is_stable(self):
        self.assertEqual(
            list_doc_topics(),
            ["index", "media", "routing", "sources", "tools", "writes"],
        )

    def test_load_routing_doc_has_facade_guidance(self):
        text = load_doc_topic("routing")

        self.assertIn("telegram_read", text)
        self.assertIn("telegram_search", text)
        self.assertNotIn("/Users/sereja", text)

    def test_unknown_topic_raises(self):
        with self.assertRaises(ValueError) as ctx:
            load_doc_topic("missing")

        self.assertIn("Unknown doc topic", str(ctx.exception))