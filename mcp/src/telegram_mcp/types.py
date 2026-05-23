"""Pydantic models for Telegram entities."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class UserInfo(BaseModel):
    id: int
    first_name: str = ""
    last_name: str = ""
    username: str | None = None
    phone: str | None = None
    is_bot: bool = False

    @property
    def display_name(self) -> str:
        name = self.first_name
        if self.last_name:
            name += f" {self.last_name}"
        return name


class Dialog(BaseModel):
    id: int
    name: str
    type: str  # "user", "group", "supergroup", "channel"
    unread_count: int = 0
    last_message_date: datetime | None = None
    is_archived: bool = False
    username: str | None = None


class DialogsResult(BaseModel):
    dialogs: list[Dialog]


class MessageInfo(BaseModel):
    id: int
    chat_id: int
    sender_id: int | None = None
    sender_name: str = ""
    date: datetime
    text: str = ""
    reply_to_msg_id: int | None = None
    is_outgoing: bool = False
    has_media: bool = False
    media_type: str | None = None
    mime_type: str | None = None
    file_size: int | None = None
    duration_seconds: int | None = None
    views: int | None = None
    forwards: int | None = None
    edit_date: datetime | None = None
    voice_transcription: str | None = None
    voice_transcription_status: str | None = None
    voice_transcription_error: str | None = None


class MessagesResult(BaseModel):
    messages: list[MessageInfo]
    voice_transcription_status: str = "not_requested"
    voice_transcription_count: int = 0
    omitted_voice_count: int = 0
    sender_resolution_count: int = 0
    truncated: bool = False
    truncated_reason: str | None = None


class DialogHandle(BaseModel):
    dialog_ref: str
    id: int
    name: str
    type: str
    username: str | None = None
    resolved_from: str
    match_confidence: float = 1.0
    candidate_count: int | None = None


class DialogSliceResult(BaseModel):
    chat: ChatInfo
    messages: list[MessageInfo]
    has_more_before: bool = False
    next_offset_id: int | None = None
    voice_transcription_status: str = "not_requested"
    voice_transcription_count: int = 0
    omitted_voice_count: int = 0
    sender_resolution_count: int = 0
    truncated: bool = False
    truncated_reason: str | None = None


class DialogReadRange(BaseModel):
    date_from: str | None = None
    date_to: str | None = None


class DialogReadResult(BaseModel):
    chat: DialogHandle
    messages: list[MessageInfo]
    message_count: int
    has_more_before: bool = False
    next_offset_id: int | None = None
    range: DialogReadRange = Field(default_factory=DialogReadRange)
    data_source: str = "live_telegram"
    voice_transcription_status: str = "not_requested"
    voice_transcription_count: int = 0
    omitted_voice_count: int = 0
    sender_resolution_count: int = 0
    truncated: bool = False
    truncated_reason: str | None = None


class DialogContextResult(BaseModel):
    chat: DialogHandle
    messages: list[MessageInfo]
    message_count: int
    pinned_messages: list[MessageInfo] = Field(default_factory=list)
    pinned_count: int = 0
    evidence_message_ids: list[int] = Field(default_factory=list)
    media_message_ids: list[int] = Field(default_factory=list)
    has_more_before: bool = False
    next_offset_id: int | None = None
    range: DialogReadRange = Field(default_factory=DialogReadRange)
    data_source: str = "live_telegram"
    collection_mode: str = "fast"
    include_voice_transcription: bool = False
    voice_transcription_status: str = "not_requested"
    voice_transcription_count: int = 0
    omitted_voice_count: int = 0
    sender_resolution_count: int = 0
    truncated: bool = False
    truncated_reason: str | None = None


class DialogReplyPreparation(BaseModel):
    chat: DialogHandle
    goal: str
    context: DialogContextResult
    evidence_message_ids: list[int] = Field(default_factory=list)
    reply_target_message_id: int | None = None
    draft_text: str | None = None
    preview_only: bool = True
    send_tool: str
    send_args_preview: dict[str, object]
    warnings: list[str] = Field(default_factory=list)


class DialogSendPreparation(BaseModel):
    chat: DialogHandle
    text: str
    parse_mode: str | None = "md"
    reply_target_message_id: int | None = None
    preview_only: bool = True
    send_tool: str
    send_args_preview: dict[str, object]
    warnings: list[str] = Field(default_factory=list)


class DialogFileSendPreparation(BaseModel):
    chat: DialogHandle
    file_path: str
    file_name: str
    caption: str = ""
    parse_mode: str | None = "md"
    preview_only: bool = True
    send_tool: str
    send_args_preview: dict[str, object]
    preview_token: str
    warnings: list[str] = Field(default_factory=list)


class ChatInfo(BaseModel):
    id: int
    name: str
    type: str
    username: str | None = None
    description: str | None = None
    participants_count: int | None = None
    is_verified: bool = False
    is_restricted: bool = False
    photo: bool = False


class Contact(BaseModel):
    id: int
    first_name: str = ""
    last_name: str = ""
    username: str | None = None
    phone: str | None = None
    is_mutual: bool = False

    @property
    def display_name(self) -> str:
        name = self.first_name
        if self.last_name:
            name += f" {self.last_name}"
        return name


class ContactsResult(BaseModel):
    contacts: list[Contact]


class TranscriptionResult(BaseModel):
    text: str
    pending: bool  # True = still processing, call again later


class MediaInfo(BaseModel):
    file_name: str | None = None
    file_size: int | None = None
    mime_type: str | None = None
    media_type: str = ""  # "photo", "document", "video", "audio", "voice", "sticker"
    local_path: str | None = None


class MediaBatchItem(BaseModel):
    message_id: int
    ok: bool
    media: MediaInfo | None = None
    error: str | None = None


class MediaBatchResult(BaseModel):
    chat_id: int
    requested_count: int
    success_count: int
    failed_count: int
    items: list[MediaBatchItem]


class MediaInspectionManifestItem(BaseModel):
    message_id: int
    chat_id: int
    date: datetime
    caption: str = ""
    media_type: str | None = None
    mime_type: str | None = None
    file_size: int | None = None
    local_path: str | None = None


class MediaInspectionManifest(BaseModel):
    chat: DialogHandle
    range: DialogReadRange = Field(default_factory=DialogReadRange)
    requested_limit: int
    message_count: int
    media_count: int
    items: list[MediaInspectionManifestItem]
    has_more_before: bool = False
    next_offset_id: int | None = None
    data_source: str = "live_telegram"
    download_tool: str = "download_dialog_media"


class LinkResult(BaseModel):
    link: str


class OperationResult(BaseModel):
    ok: bool = True
    message: str


class HealthInfo(BaseModel):
    connected: bool
    authorized: bool
    session_backend: str
    shared_client: bool
    transport: str = "stdio"
    entity_cache_size: int = 0
    download_dir: str
    session_path: str | None = None
    host: str | None = None
    port: int | None = None
    http_path: str | None = None
    endpoint_url: str | None = None
    scheduler: dict[str, dict[str, object]] | None = None
    runtime_stats: dict[str, object] | None = None


class DoctorInfo(BaseModel):
    status: str
    transport: str
    session_backend: str
    checks: dict[str, str]
    warnings: list[str]
    download_cleanup: dict[str, object] | None = None
    host: str | None = None
    port: int | None = None
    http_path: str | None = None
    endpoint_url: str | None = None
    scheduler: dict[str, dict[str, object]] | None = None
    runtime_stats: dict[str, object] | None = None


class StoryViewInfo(BaseModel):
    user_id: int
    user_name: str = ""
    date: datetime
    reaction: str | None = None


class StoryViewsStats(BaseModel):
    views_count: int
    forwards_count: int = 0
    reactions_count: int = 0
    recent_viewers: list[int] = []


class StoryInfo(BaseModel):
    id: int
    peer_id: int
    date: datetime
    expire_date: datetime | None = None
    caption: str = ""
    has_media: bool = False
    media_type: str | None = None  # "photo" | "video"
    views: StoryViewsStats | None = None
    pinned: bool = False
    public: bool = False
    is_outgoing: bool = False
    close_friends: bool = False


class StoriesResult(BaseModel):
    stories: list[StoryInfo]


class StoryViewsResult(BaseModel):
    stats: list[StoryViewsStats]


class StoryViewersResult(BaseModel):
    viewers: list[StoryViewInfo]


# ── Group management ──


class Participant(BaseModel):
    id: int
    first_name: str = ""
    last_name: str = ""
    username: str | None = None
    role: str = "member"  # "creator", "admin", "member", "banned", "left"
    is_bot: bool = False


class ParticipantsResult(BaseModel):
    participants: list[Participant]
    total: int | None = None


class InviteLinkInfo(BaseModel):
    link: str
    creator_id: int | None = None
    expires: datetime | None = None
    usage_limit: int | None = None
    usage_count: int = 0


# ── Profile ──


class UserStatus(BaseModel):
    user_id: int
    status: str  # "online", "offline", "recently", "last_week", "last_month", "long_ago", "unknown"
    last_online: datetime | None = None


class UserPhoto(BaseModel):
    photo_id: int
    date: datetime
    has_video: bool = False


class UserPhotosResult(BaseModel):
    photos: list[UserPhoto]
    total: int = 0


# ── Polls ──


class PollInfo(BaseModel):
    message_id: int
    chat_id: int
    question: str
    options: list[str]
    is_quiz: bool = False
    multiple_choice: bool = False
    public_voters: bool = False


# ── Blocked users ──


class BlockedUsersResult(BaseModel):
    users: list[Contact]
    total: int = 0
