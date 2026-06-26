import unittest
from types import SimpleNamespace

from telegram_mcp.client_groups import GroupOperationsMixin


class _InviteLinkWrapper(GroupOperationsMixin):
    def __init__(self) -> None:
        self.write_label = None
        self.read_called = False

    async def _resolve_input_entity(self, chat):
        return f"peer:{chat}"

    async def _run_read(self, label, factory):
        self.read_called = True
        raise AssertionError(f"{label} should not use read lane")

    async def _run_write(self, label, factory):
        self.write_label = label
        return SimpleNamespace(link="https://t.me/+invite", expire_date=None, usage_limit=None, usage=0)


class GroupOperationsTests(unittest.IsolatedAsyncioTestCase):
    async def test_get_invite_link_uses_write_lane(self) -> None:
        wrapper = _InviteLinkWrapper()

        result = await wrapper.get_invite_link("@target")

        self.assertEqual(wrapper.write_label, "get_invite_link")
        self.assertFalse(wrapper.read_called)
        self.assertEqual(result.link, "https://t.me/+invite")


if __name__ == "__main__":
    unittest.main()
