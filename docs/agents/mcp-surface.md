# Default MCP Surface (16 tools)

Only these are exposed to agents via plugin allowlist: `telegram_read`,
`telegram_search`, `telegram_prepare_reply`, `telegram_confirmed_send`,
`telegram_inspect_media`, `telegram_export_members`, `resolve_dialog`,
`find_dialog`, `collect_dialog_context`, `collect_context`, `download_media`,
`download_media_batch`, `download_dialog_media`, `prepare_media_inspection_manifest`,
`get_me`, `doctor_check`. Legacy aliases (`read_today_dialog`, `prepare_dialog_reply`,
`draft_reply`, `search_dialog_messages`, …) and raw `send_dialog_message` /
`reply_in_dialog` are **not** on the default surface (full/admin profile only).

If `telegram-mcp-surface --json` reports a larger backend `tool_count`, do not
treat that alone as drift. The default profile is healthy when
`default_surface_tools` matches these 16 approved tools and
`unexpected_write_or_destructive_tools` is empty.

## Naming note

- `telegram-release-gate` **runs** the bundled pre-release gates.
- `telegram-release-gates` **audits** the gate configuration only.
