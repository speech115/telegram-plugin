# Telegram agent docs (MCP resources)

Fetch routing and safety docs via MCP resources instead of loading the full skill.

## URIs

| URI | When to read |
| --- | --- |
| `telegram://docs/index` | This file — catalog of docs |
| `telegram://docs/routing` | Before the first tool call on a Telegram task |
| `telegram://docs/tools` | When unsure which facade tool to use |
| `telegram://docs/sources` | Before mirror or archive evidence |
| `telegram://docs/writes` | Before send/reply or preview-to-send |
| `telegram://docs/media` | Before describing photos, video, stickers, or voice |

## Speed order

1. Classify: live vs historical vs write.
2. Low-stakes today read: `telegram_read(mode="fast")` or host fast adapter.
3. Search: `telegram_search` — not broad reads.
4. Metadata: `telegram_count_*`, `telegram_list_*`, `telegram_latest_message`, `telegram_dialog_metadata` — no broad history download.
5. Escalate to `mode="full"` or paging only when the user needs completeness.

## Live data

`telegram://me` returns current account JSON (cache-friendly).
