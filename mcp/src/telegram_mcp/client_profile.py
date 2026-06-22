"""Profile operations for TelegramWrapper."""

from __future__ import annotations

from telethon.tl.functions.account import UpdateProfileRequest
from telethon.tl.functions.photos import DeletePhotosRequest, GetUserPhotosRequest
from telethon.tl.types import (
    InputUser,
    User,
    UserStatusEmpty,
    UserStatusLastMonth,
    UserStatusLastWeek,
    UserStatusOffline,
    UserStatusOnline,
    UserStatusRecently,
)

from .types import UserPhoto, UserStatus


class ProfileOperationsMixin:
    """Own-profile and user profile operations."""

    async def update_profile(
        self,
        first_name: str | None = None,
        last_name: str | None = None,
        about: str | None = None,
    ) -> bool:
        kwargs = {}
        if first_name is not None:
            kwargs["first_name"] = first_name
        if last_name is not None:
            kwargs["last_name"] = last_name
        if about is not None:
            kwargs["about"] = about
        if not kwargs:
            raise ValueError("At least one field must be provided")
        await self._run_write(
            "update_profile",
            lambda: self.client(UpdateProfileRequest(**kwargs)),
        )
        return True

    async def delete_profile_photo(self) -> bool:
        me = await self._run_read("delete_profile_photo_get_me", self.client.get_me)
        if me.photo:
            photos = await self._run_read(
                "delete_profile_photo_get_photos",
                lambda: self.client(
                    GetUserPhotosRequest(
                        user_id=InputUser(
                            user_id=me.id,
                            access_hash=me.access_hash or 0,
                        ),
                        offset=0,
                        max_id=0,
                        limit=1,
                    )
                ),
            )
            if photos.photos:
                from telethon.tl.types import InputPhoto

                photo = photos.photos[0]
                await self._run_write(
                    "delete_profile_photo",
                    lambda: self.client(
                        DeletePhotosRequest(
                            id=[
                                InputPhoto(
                                    id=photo.id,
                                    access_hash=photo.access_hash,
                                    file_reference=photo.file_reference,
                                )
                            ]
                        )
                    ),
                )
        return True

    async def get_user_photos(
        self,
        user_id: int,
        limit: int = 10,
    ) -> tuple[list[UserPhoto], int]:
        self._validate_non_negative("limit", limit)
        entity = await self.client.get_input_entity(user_id)
        result = await self._run_read(
            "get_user_photos",
            lambda: self.client(
                GetUserPhotosRequest(user_id=entity, offset=0, max_id=0, limit=limit)
            ),
        )
        photos = []
        for photo in result.photos:
            photos.append(
                UserPhoto(
                    photo_id=photo.id,
                    date=photo.date,
                    has_video=getattr(photo, "has_video", False) or False,
                )
            )
        return photos, result.count

    async def get_user_status(self, user_id: int) -> UserStatus:
        entity = await self._run_read(
            "get_user_status",
            lambda: self.client.get_entity(user_id),
        )
        if not isinstance(entity, User):
            raise ValueError("Can only get status for users")

        status_obj = entity.status
        status = "unknown"
        last_online = None

        if isinstance(status_obj, UserStatusOnline):
            status = "online"
        elif isinstance(status_obj, UserStatusOffline):
            status = "offline"
            last_online = status_obj.was_online
        elif isinstance(status_obj, UserStatusRecently):
            status = "recently"
        elif isinstance(status_obj, UserStatusLastWeek):
            status = "last_week"
        elif isinstance(status_obj, UserStatusLastMonth):
            status = "last_month"
        elif isinstance(status_obj, UserStatusEmpty) or status_obj is None:
            status = "long_ago"

        return UserStatus(
            user_id=entity.id,
            status=status,
            last_online=last_online,
        )
