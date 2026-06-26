"""Group and channel management operations for TelegramWrapper."""

from __future__ import annotations

from telethon.tl.functions.channels import (
    CreateChannelRequest,
    EditAdminRequest,
    EditBannedRequest,
    EditPhotoRequest as EditChannelPhotoRequest,
    EditTitleRequest as EditChannelTitleRequest,
    GetParticipantsRequest,
    InviteToChannelRequest,
    LeaveChannelRequest,
)
from telethon.tl.functions.messages import (
    AddChatUserRequest,
    CreateChatRequest,
    DeleteChatUserRequest,
    EditChatPhotoRequest,
    EditChatTitleRequest,
    ExportChatInviteRequest,
)
from telethon.tl.types import (
    Channel,
    ChannelParticipantsAdmins,
    ChannelParticipantsBanned,
    ChannelParticipantsSearch,
    Chat,
    ChatAdminRights,
    ChatBannedRights,
    InputChatPhotoEmpty,
    User,
)

from .types import ChatInfo, InviteLinkInfo, Participant
from .utils import get_display_name, get_entity_type


class GroupOperationsMixin:
    """Group and channel administration operations."""

    # ── Group management ──

    async def create_group(self, title: str, user_ids: list[int]) -> ChatInfo:
        users = [await self.client.get_input_entity(uid) for uid in user_ids]
        result = await self._run_write(
            "create_group",
            lambda: self.client(CreateChatRequest(users=users, title=title)),
        )
        chat = result.chats[0]
        self._invalidate_chat_list_cache()
        return ChatInfo(
            id=chat.id,
            name=chat.title or title,
            type="group",
        )

    async def create_channel(
        self, title: str, about: str = "", megagroup: bool = False
    ) -> ChatInfo:
        result = await self._run_write(
            "create_channel",
            lambda: self.client(
                CreateChannelRequest(title=title, about=about, megagroup=megagroup)
            ),
        )
        ch = result.chats[0]
        self._invalidate_chat_list_cache()
        return ChatInfo(
            id=ch.id,
            name=ch.title or title,
            type="supergroup" if megagroup else "channel",
            description=about or None,
        )

    async def edit_chat_title(self, chat: str | int, title: str) -> bool:
        entity = await self._resolve_entity(chat)
        if isinstance(entity, Channel):
            await self._run_write(
                "edit_chat_title",
                lambda: self.client(EditChannelTitleRequest(channel=entity, title=title)),
            )
        elif isinstance(entity, Chat):
            await self._run_write(
                "edit_chat_title",
                lambda: self.client(EditChatTitleRequest(chat_id=entity.id, title=title)),
            )
        else:
            raise ValueError("Cannot edit title of a user chat")
        self.invalidate_cache("get_chat_info")
        self._invalidate_chat_list_cache()
        return True
    async def delete_chat_photo(self, chat: str | int) -> bool:
        entity = await self._resolve_entity(chat)
        if isinstance(entity, Channel):
            await self._run_write(
                "delete_chat_photo",
                lambda: self.client(EditChannelPhotoRequest(channel=entity, photo=InputChatPhotoEmpty())),
            )
        elif isinstance(entity, Chat):
            await self._run_write(
                "delete_chat_photo",
                lambda: self.client(EditChatPhotoRequest(chat_id=entity.id, photo=InputChatPhotoEmpty())),
            )
        else:
            raise ValueError("Cannot delete photo of a user chat")
        return True

    async def leave_chat(self, chat: str | int) -> bool:
        entity = await self._resolve_entity(chat)
        if isinstance(entity, Channel):
            await self._run_write(
                "leave_chat",
                lambda: self.client(LeaveChannelRequest(channel=entity)),
            )
        elif isinstance(entity, Chat):
            me = await self.client.get_me()
            await self._run_write(
                "leave_chat",
                lambda: self.client(DeleteChatUserRequest(chat_id=entity.id, user_id=me)),
            )
        else:
            raise ValueError("Cannot leave a user chat")
        self._invalidate_chat_list_cache()
        return True

    def _user_to_participant(self, user: User, role: str = "member") -> Participant:
        return Participant(
            id=user.id,
            first_name=user.first_name or "",
            last_name=user.last_name or "",
            username=user.username,
            role=role,
            is_bot=user.bot or False,
        )

    async def get_participants(
        self, chat: str | int, limit: int = 200
    ) -> tuple[list[Participant], int | None]:
        self._validate_non_negative("limit", limit)
        entity = await self._resolve_entity(chat)
        participants = []
        total = None
        if isinstance(entity, Channel):
            result = await self._run_read(
                "get_participants",
                lambda: self.client(
                    GetParticipantsRequest(
                        channel=entity,
                        filter=ChannelParticipantsSearch(""),
                        offset=0,
                        limit=limit,
                        hash=0,
                    )
                ),
            )
            total = result.count
            users_map = {u.id: u for u in result.users}
            for p in result.participants:
                user = users_map.get(p.user_id)
                if user:
                    role = "member"
                    ptype = type(p).__name__
                    if "Creator" in ptype:
                        role = "creator"
                    elif "Admin" in ptype:
                        role = "admin"
                    elif "Banned" in ptype:
                        role = "banned"
                    participants.append(self._user_to_participant(user, role))
        else:
            async for user in self.client.iter_participants(entity, limit=limit):
                role = "member"
                if hasattr(user, "participant"):
                    ptype = type(user.participant).__name__
                    if "Creator" in ptype:
                        role = "creator"
                    elif "Admin" in ptype:
                        role = "admin"
                participants.append(self._user_to_participant(user, role))
        return participants, total

    async def get_admins(
        self, chat: str | int, limit: int = 200
    ) -> list[Participant]:
        entity = await self._resolve_entity(chat)
        admins = []
        if isinstance(entity, Channel):
            result = await self._run_read(
                "get_admins",
                lambda: self.client(
                    GetParticipantsRequest(
                        channel=entity,
                        filter=ChannelParticipantsAdmins(),
                        offset=0,
                        limit=limit,
                        hash=0,
                    )
                ),
            )
            users_map = {u.id: u for u in result.users}
            for p in result.participants:
                user = users_map.get(p.user_id)
                if user:
                    role = "creator" if "Creator" in type(p).__name__ else "admin"
                    admins.append(self._user_to_participant(user, role))
        else:
            async for user in self.client.iter_participants(entity, aggressive=False, limit=limit):
                ptype = type(getattr(user, "participant", None)).__name__
                if "Creator" in ptype or "Admin" in ptype:
                    role = "creator" if "Creator" in ptype else "admin"
                    admins.append(self._user_to_participant(user, role))
        return admins

    async def get_banned_users(
        self, chat: str | int, limit: int = 200
    ) -> list[Participant]:
        entity = await self._resolve_entity(chat)
        banned = []
        if isinstance(entity, Channel):
            result = await self._run_read(
                "get_banned_users",
                lambda: self.client(
                    GetParticipantsRequest(
                        channel=entity,
                        filter=ChannelParticipantsBanned(""),
                        offset=0,
                        limit=limit,
                        hash=0,
                    )
                ),
            )
            users_map = {u.id: u for u in result.users}
            for p in result.participants:
                user = users_map.get(p.user_id)
                if user:
                    banned.append(self._user_to_participant(user, "banned"))
        return banned

    async def promote_admin(
        self, chat: str | int, user_id: int, rights: dict[str, bool] | None = None
    ) -> bool:
        entity = await self._resolve_entity(chat)
        user = await self.client.get_input_entity(user_id)
        default_rights = ChatAdminRights(
            change_info=True,
            delete_messages=True,
            ban_users=True,
            invite_users=True,
            pin_messages=True,
            manage_call=True,
        )
        if rights:
            default_rights = ChatAdminRights(**rights)
        if isinstance(entity, Channel):
            await self._run_write(
                "promote_admin",
                lambda: self.client(
                    EditAdminRequest(
                        channel=entity,
                        user_id=user,
                        admin_rights=default_rights,
                        rank="",
                    )
                ),
            )
        else:
            raise ValueError("promote_admin only works for channels/supergroups")
        return True

    async def demote_admin(self, chat: str | int, user_id: int) -> bool:
        entity = await self._resolve_entity(chat)
        user = await self.client.get_input_entity(user_id)
        if isinstance(entity, Channel):
            await self._run_write(
                "demote_admin",
                lambda: self.client(
                    EditAdminRequest(
                        channel=entity,
                        user_id=user,
                        admin_rights=ChatAdminRights(),
                        rank="",
                    )
                ),
            )
        else:
            raise ValueError("demote_admin only works for channels/supergroups")
        return True

    async def ban_user(self, chat: str | int, user_id: int) -> bool:
        entity = await self._resolve_entity(chat)
        user = await self.client.get_input_entity(user_id)
        if isinstance(entity, Channel):
            await self._run_write(
                "ban_user",
                lambda: self.client(
                    EditBannedRequest(
                        channel=entity,
                        participant=user,
                        banned_rights=ChatBannedRights(
                            until_date=None,
                            view_messages=True,
                            send_messages=True,
                            send_media=True,
                            send_stickers=True,
                            send_gifs=True,
                            send_games=True,
                            send_inline=True,
                            embed_links=True,
                        ),
                    )
                ),
            )
        elif isinstance(entity, Chat):
            await self._run_write(
                "ban_user",
                lambda: self.client(DeleteChatUserRequest(chat_id=entity.id, user_id=user)),
            )
        else:
            raise ValueError("Cannot ban user in a private chat")
        return True

    async def unban_user(self, chat: str | int, user_id: int) -> bool:
        entity = await self._resolve_entity(chat)
        user = await self.client.get_input_entity(user_id)
        if isinstance(entity, Channel):
            await self._run_write(
                "unban_user",
                lambda: self.client(
                    EditBannedRequest(
                        channel=entity,
                        participant=user,
                        banned_rights=ChatBannedRights(),
                    )
                ),
            )
        else:
            raise ValueError("unban_user only works for channels/supergroups")
        return True

    async def get_invite_link(self, chat: str | int) -> InviteLinkInfo:
        peer = await self._resolve_input_entity(chat)
        result = await self._run_write(
            "get_invite_link",
            lambda: self.client(ExportChatInviteRequest(peer=peer)),
        )
        return InviteLinkInfo(
            link=result.link,
            expires=getattr(result, "expire_date", None),
            usage_limit=getattr(result, "usage_limit", None),
            usage_count=getattr(result, "usage", 0) or 0,
        )

    async def invite_to_group(
        self, chat: str | int, user_ids: list[int]
    ) -> bool:
        entity = await self._resolve_entity(chat)
        if isinstance(entity, Channel):
            users = [await self.client.get_input_entity(uid) for uid in user_ids]
            await self._run_write(
                "invite_to_group",
                lambda: self.client(InviteToChannelRequest(channel=entity, users=users)),
            )
        elif isinstance(entity, Chat):
            for uid in user_ids:
                user = await self.client.get_input_entity(uid)
                await self._run_write(
                    "invite_to_group",
                    lambda: self.client(
                        AddChatUserRequest(chat_id=entity.id, user_id=user, fwd_limit=50)
                    ),
                )
        else:
            raise ValueError("Cannot invite users to a private chat")
        return True
