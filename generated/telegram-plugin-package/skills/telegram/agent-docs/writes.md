# Write safety

## Hard stops

- Never call raw `send_dialog_message` / `reply_in_dialog` on the default surface.
- Writes require explicit user intent, unambiguous target, exact message text (or reply id).
- Resolve stable identity (`dialog_ref`, `@username`, or numeric peer id) before send.
- Pronouns, first names, or "the last chat" are not enough for writes.
- Preview tools never grant send permission by themselves.

## Preview → send

- After `prepare_*`, open `human_approval_url` and click **Approve** before any send.
- Prefer `telegram_confirmed_send(preview_id=...)` from the preview; legacy path needs
  matching `confirmation_token` and exact text.
- "Send it" is valid only in the **same turn** with unchanged target, reply id, and text.
- If context changed the draft, prepare a new preview or ask the user.

## Intent matrix

| User wording | Action |
| --- | --- |
| "что ответить", "draft" | draft only |
| "preview", "покажи перед отправкой" | non-sending preview |
| "отправь: …" with exact text + target | preview if useful, then `telegram_confirmed_send` |
| fuzzy target, changed draft, stale preview | ask — do not send |