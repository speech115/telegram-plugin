# Default facade tools

The restricted plugin profile exposes task-shaped tools only. Prefer these names.

## Read / search

- `telegram_read`
- `telegram_search`
- `telegram_count_posts`
- `telegram_count_photos`
- `telegram_count_videos`
- `telegram_count_documents`
- `telegram_count_voice`
- `telegram_count_pinned`
- `telegram_count_gifs`
- `telegram_count_music`
- `telegram_count_links`
- `telegram_count_polls`
- `telegram_count_geo`
- `telegram_count_round_video`
- `telegram_count_round_voice`
- `telegram_count_chat_photos`
- `telegram_count_mentions`
- `telegram_list_gifs`
- `telegram_list_music`
- `telegram_list_links`
- `telegram_list_polls`
- `telegram_list_geo`
- `telegram_latest_message`
- `telegram_dialog_metadata`
- `telegram_get_message`
- `resolve_dialog`
- `find_dialog`
- `collect_dialog_context`
- `collect_context`
- `get_me`
- `doctor_check`

## Prepare / write

- `telegram_prepare_reply`
- `telegram_confirmed_send`

## Media / export

- `telegram_inspect_media`
- `prepare_media_inspection_manifest`
- `download_media`
- `download_media_batch`
- `download_dialog_media`

## Not on default surface

Low-level aliases such as `read_today_dialog`, `send_dialog_message`, and admin
mutations require an explicit full/admin profile. Agents on the default surface
must not call them.

`telegram_export_members` is an explicit owner/local privacy export. It remains
available in the full owner surface, but it is not routine default-facade context
gathering.

## Modes for `telegram_read`

- `fast` — no voice transcription, no sender names (default for skim)
- `full` — sender names; use when quotes, attribution, or voice matter
