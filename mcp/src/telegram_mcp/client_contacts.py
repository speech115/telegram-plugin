"""Contact operations for TelegramWrapper."""

from __future__ import annotations

from telethon.tl.functions.contacts import (
    BlockRequest,
    DeleteContactsRequest,
    GetBlockedRequest,
    GetContactsRequest,
    ImportContactsRequest,
    SearchRequest,
    UnblockRequest,
)
from telethon.tl.types import InputPhoneContact, User

from .types import Contact


class ContactOperationsMixin:
    """Contact lookup and management operations."""

    async def list_contacts(self) -> list[Contact]:
        cached = self._cache_get("list_contacts")
        if cached is not None:
            return cached
        result = await self._run_read(
            "list_contacts",
            lambda: self.client(GetContactsRequest(hash=0)),
        )
        contacts = []
        for user in result.users:
            contacts.append(
                Contact(
                    id=user.id,
                    first_name=user.first_name or "",
                    last_name=user.last_name or "",
                    username=user.username,
                    phone=user.phone,
                    is_mutual=getattr(user, "mutual_contact", False) or False,
                )
            )
        self._cache_set("list_contacts", contacts)
        return contacts

    async def search_contacts(self, query: str, limit: int = 20) -> list[Contact]:
        self._validate_non_negative("limit", limit)
        result = await self._run_read(
            "search_contacts",
            lambda: self.client(SearchRequest(q=query, limit=limit)),
        )
        contacts = []
        for user in result.users:
            if isinstance(user, User):
                contacts.append(
                    Contact(
                        id=user.id,
                        first_name=user.first_name or "",
                        last_name=user.last_name or "",
                        username=user.username,
                        phone=user.phone,
                        is_mutual=getattr(user, "mutual_contact", False) or False,
                    )
                )
        return contacts

    async def add_contact(
        self,
        phone: str,
        first_name: str,
        last_name: str = "",
    ) -> Contact:
        result = await self._run_write(
            "add_contact",
            lambda: self.client(
                ImportContactsRequest(
                    contacts=[
                        InputPhoneContact(
                            client_id=0,
                            phone=phone,
                            first_name=first_name,
                            last_name=last_name,
                        )
                    ]
                )
            ),
        )
        if result.users:
            user = result.users[0]
            self.invalidate_cache("list_contacts")
            return Contact(
                id=user.id,
                first_name=user.first_name or "",
                last_name=user.last_name or "",
                username=user.username,
                phone=user.phone,
            )
        raise ValueError("Contact not found on Telegram")

    async def delete_contact(self, user_id: int) -> bool:
        user = await self.client.get_input_entity(user_id)
        await self._run_write(
            "delete_contact",
            lambda: self.client(DeleteContactsRequest(id=[user])),
        )
        self.invalidate_cache("list_contacts")
        return True

    async def block_user(self, user_id: int) -> bool:
        user = await self.client.get_input_entity(user_id)
        await self._run_write(
            "block_user",
            lambda: self.client(BlockRequest(id=user)),
        )
        return True

    async def unblock_user(self, user_id: int) -> bool:
        user = await self.client.get_input_entity(user_id)
        await self._run_write(
            "unblock_user",
            lambda: self.client(UnblockRequest(id=user)),
        )
        return True

    async def get_blocked_users(self, limit: int = 100) -> tuple[list[Contact], int]:
        self._validate_non_negative("limit", limit)
        result = await self._run_read(
            "get_blocked_users",
            lambda: self.client(GetBlockedRequest(offset=0, limit=limit)),
        )
        users_map = {user.id: user for user in result.users}
        contacts = []
        for blocked in result.blocked:
            user = users_map.get(blocked.peer_id.user_id)
            if user and isinstance(user, User):
                contacts.append(
                    Contact(
                        id=user.id,
                        first_name=user.first_name or "",
                        last_name=user.last_name or "",
                        username=user.username,
                        phone=user.phone,
                    )
                )
        return contacts, getattr(result, "count", len(contacts))

    async def import_contacts(self, contacts: list[dict[str, str]]) -> int:
        input_contacts = [
            InputPhoneContact(
                client_id=i,
                phone=contact["phone"],
                first_name=contact.get("first_name", ""),
                last_name=contact.get("last_name", ""),
            )
            for i, contact in enumerate(contacts)
        ]
        result = await self._run_write(
            "import_contacts",
            lambda: self.client(ImportContactsRequest(contacts=input_contacts)),
        )
        self.invalidate_cache("list_contacts")
        return len(result.imported)
