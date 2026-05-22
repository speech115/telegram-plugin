"""Contact management tools."""

from __future__ import annotations

from mcp.types import ToolAnnotations

from .. import runtime
from ..errors import tool_error_handler
from ..types import BlockedUsersResult, Contact, ContactsResult, OperationResult

READONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True)
ADDITIVE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True)
DESTRUCTIVE = ToolAnnotations(readOnlyHint=False, destructiveHint=True, openWorldHint=True)
IDEMPOTENT = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=True)


async def list_contacts() -> ContactsResult:
    """List all Telegram contacts."""
    tg = await runtime.get_tg()
    contacts = await tg.list_contacts()
    return ContactsResult(contacts=contacts)


async def search_contacts(query: str, limit: int = 20) -> ContactsResult:
    """Search contacts by name or username."""
    tg = await runtime.get_tg()
    contacts = await tg.search_contacts(query=query, limit=limit)
    return ContactsResult(contacts=contacts)


async def add_contact(
    phone: str, first_name: str, last_name: str = ""
) -> Contact:
    """Add a contact by phone number."""
    tg = await runtime.get_tg()
    return await tg.add_contact(phone=phone, first_name=first_name, last_name=last_name)


async def delete_contact(user_id: int) -> OperationResult:
    """Remove a contact from your contact list."""
    tg = await runtime.get_tg()
    await tg.delete_contact(user_id=user_id)
    return OperationResult(message=f"Contact {user_id} deleted")


async def set_user_blocked(user_id: int, blocked: bool = True) -> OperationResult:
    """Block or unblock a user."""
    tg = await runtime.get_tg()
    if blocked:
        await tg.block_user(user_id=user_id)
        return OperationResult(message=f"User {user_id} blocked")
    else:
        await tg.unblock_user(user_id=user_id)
        return OperationResult(message=f"User {user_id} unblocked")


async def get_blocked_users(limit: int = 100) -> BlockedUsersResult:
    """Get list of blocked users."""
    tg = await runtime.get_tg()
    users, total = await tg.get_blocked_users(limit=limit)
    return BlockedUsersResult(users=users, total=total)


async def import_contacts(
    contacts: list[dict[str, str]],
) -> OperationResult:
    """Bulk import contacts."""
    tg = await runtime.get_tg()
    count = await tg.import_contacts(contacts=contacts)
    return OperationResult(message=f"Imported {count} contact(s)")


def register(mcp) -> None:
    mcp.tool(annotations=READONLY)(tool_error_handler(list_contacts))
    mcp.tool(annotations=READONLY)(tool_error_handler(search_contacts))
    mcp.tool(annotations=ADDITIVE)(tool_error_handler(add_contact))
    mcp.tool(annotations=DESTRUCTIVE)(tool_error_handler(delete_contact))
    mcp.tool(annotations=DESTRUCTIVE)(tool_error_handler(set_user_blocked))
    mcp.tool(annotations=READONLY)(tool_error_handler(get_blocked_users))
    mcp.tool(annotations=ADDITIVE)(tool_error_handler(import_contacts))
