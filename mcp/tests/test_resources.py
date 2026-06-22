import unittest
from unittest.mock import AsyncMock, patch

import telegram_mcp.server  # noqa: F401  Ensures resources are registered.
from telegram_mcp.resources import agent_doc_resource, me_resource
from telegram_mcp.runtime import mcp
from telegram_mcp.types import UserInfo


def _run(awaitable):
    import asyncio

    return asyncio.run(awaitable)


class ResourceTests(unittest.TestCase):
    def test_me_resource_returns_structured_payload(self):
        wrapper = AsyncMock()
        wrapper.get_me.return_value = UserInfo(
            id=1,
            first_name="Sereja",
            username="sereja",
        )

        with patch("telegram_mcp.resources.get_tg", AsyncMock(return_value=wrapper)):
            result = _run(me_resource())

        self.assertIsInstance(result, dict)
        self.assertEqual(result["username"], "sereja")

    def test_me_resource_uses_application_json_mime_type(self):
        resource = next(
            r for r in mcp._resource_manager.list_resources()
            if str(r.uri) == "telegram://me"
        )

        self.assertEqual(resource.mime_type, "application/json")

    def test_agent_doc_template_is_registered(self):
        template = next(
            t
            for t in mcp._resource_manager.list_templates()
            if t.uri_template == "telegram://docs/{topic}"
        )

        self.assertEqual(template.mime_type, "text/markdown")
        self.assertIn("routing", template.description)

    def test_agent_doc_resource_returns_routing_markdown(self):
        text = agent_doc_resource("routing")

        self.assertIn("# Full MCP Routing", text)
        self.assertIn("telegram_read", text)
