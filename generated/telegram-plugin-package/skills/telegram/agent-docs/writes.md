# Write safety

## Hard stops

- Prefer direct full MCP write tools: `telegram_send`, `send_message`,
  `reply_to_message`, `edit_message`, `delete_messages`, `forward_messages`,
  `set_message_pinned`, and `send_reaction`.
- Writes require explicit user intent, unambiguous target, exact message text (or reply id).
- Resolve stable identity (`dialog_ref`, `@username`, or numeric peer id) before send.
- Pronouns, first names, or "the last chat" are not enough for writes.
- Preview tools never grant send permission by themselves.

## Preview → send

- Normal local sends do not require browser approval. Use
  `telegram_send` / `send_message` when the target and exact text are explicit.
- If the user asks for a preview first, use `prepare_*`; then send only if the
  same-turn target, reply id, and text are unchanged.
- "Send it" is valid only in the **same turn** with unchanged target, reply id, and text.
- If context changed the draft, prepare a new preview or ask the user.

## Intent matrix

| User wording | Action |
| --- | --- |
| "что ответить", "draft" | draft only |
| "preview", "покажи перед отправкой" | non-sending preview |
| "отправь: …" with exact text + target | direct `telegram_send` / `send_message` |
| fuzzy target, changed draft, stale preview | ask — do not send |
