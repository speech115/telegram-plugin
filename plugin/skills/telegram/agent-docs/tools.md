# Default facade tools

The restricted plugin profile exposes task-shaped tools only. Prefer these names.

## Read / search

- `telegram_read`
- `telegram_search`
- `telegram_count_posts`
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
- `telegram_export_members`

## Not on default surface

Low-level aliases such as `read_today_dialog`, `send_dialog_message`, and admin
mutations require an explicit full/admin profile. Agents on the default surface
must not call them.

## Modes for `telegram_read`

- `fast` — no voice transcription, no sender names (default for skim)
- `full` — sender names; use when quotes, attribution, or voice matter
