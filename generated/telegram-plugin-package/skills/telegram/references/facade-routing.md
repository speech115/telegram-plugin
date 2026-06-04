# Facade Routing

## Fast Defaults

- Live/current tasks require live MCP facade tools or aliases. If they are not
  exposed in the current chat tool surface, first try a host-configured local
  read-only shortcut when available. This portable plugin package intentionally
  does not hardcode machine-local adapter paths.
  Only report live Telegram unavailable after both the exposed facade path and
  the bounded local MCP shortcut fail. Do not replace a current-state answer
  with mirror or archive evidence.
- On hosts with the local `tg` CLI on PATH, use it first for live reads (no
  `@telegram`, no plugin bootstrap):
  - `tg read today <chat> --limit 30 --json`
  - `tg read recent <chat> --limit 30 --json`
  - `tg search <chat> "<query>" --limit 20 --json`
- Fallback shortcut: `telegram-fast-read-today`. Use MCP facade for writes,
  media inspection, subscriber export, fuzzy identity work, or complete-context paging.
- Scoped one-on-one reads like "прочитай переписку с @user за сегодня с HH:MM"
  should complete in one fast pass: read the requested local calendar day with
  `include_voice_transcription=false`, `include_sender_name=false`, and a
  bounded timeout. If the read payload returns a canonical `dialog_ref`, reuse it
  for any follow-up call. If the start time is near local midnight, also read
  the previous UTC calendar day before summarizing. Do not inspect media, page,
  run repo/vault checks, or use `mcporter` unless the text evidence or a real
  MCP failure requires it.
- Quick orientation: `collect_dialog_context(mode="fast", recent_limit=15-30, include_pinned=false)`.
- Date-specific today reads: use `telegram_read(day=...)` instead of manually computing today's range.
- One-on-one fast reads: pass `include_sender_name=false` unless speaker identity is unclear.
- Groups: keep sender names when attribution matters.
- Reuse the canonical `dialog_ref` returned by the first facade call for follow-up calls.
- Use `mode="full"` only when sender names, voice transcripts, pinned messages, or richer evidence are needed.
- Do not call `tool_search`, read plugin README files, inspect launchd configs,
  or run broad Telegram status commands before a simple low-stakes today read.
- If the default endpoint has a transient timeout but an alternate configured
  live MCP profile succeeds on `get_me`, use the healthy profile immediately;
  do not spend multiple rounds proving the unhealthy profile is broken.

## Read result cache hints

- `telegram_read` and `collect_dialog_context` may return `result_cache_hit`,
  `result_cache_age_seconds`, and `result_cache_ttl_seconds` (in-process dialog
  read cache inside one MCP server worker).
- HTTP MCP usually handles each tool call in a fresh worker: expect
  `result_cache_hit=false` on back-to-back identical reads. Do not repeat the
  same read just to "warm" cache over HTTP.
- Within one long-lived MCP session, a repeated identical read may show
  `result_cache_hit=true` with a small `result_cache_age_seconds`.

## App-Style Aliases

When exposed by the current host, app-style aliases are thin wrappers over the dialog facade:

- `find_dialog` -> `resolve_dialog`
- `read_dialog` -> `telegram_read` when `day` is set, otherwise recent dialog read
- `collect_context` -> `collect_dialog_context`
- Legacy (full profile only): `draft_reply` -> `prepare_dialog_reply` -> prefer `telegram_prepare_reply` on default surface
- `reply_message` -> `reply_in_dialog`

Prefer canonical facade names in agent routing unless the host exposes only the aliases.

## Avoid Double Work

- Do not call `resolve_dialog` after a facade read already returned `chat.dialog_ref`.
- Do not follow `collect_dialog_context` with another broad read for the same window unless needed parameters were missing.
- Do not follow `telegram_prepare_reply` with a separate context read unless warnings say the context is incomplete or the user asks for more evidence.
- Do not use `telegram_read` for keyword lookup. Use `telegram_search` or `search_dialog_messages` first.
- Do not fetch pinned messages on the first pass unless the user mentions rules, instructions, pinned items, group setup, or long-running project context.
- Do not page just because `has_more_before=true`; page only when the user asked for completeness or current evidence is insufficient.

## Escalation

- If `has_more_before=true` or `truncated=true` and the user asked for complete context, page with `next_offset_id` or `offset_id` using the same facade tool.
- If `voice_transcription_status` is `partial`, `omitted`, or `failed` and the voice content could change the answer, call `transcribe_voice` only for needed message ids.
- If `media_message_ids` is non-empty and the user asked about visuals, download and inspect the files.
- If media exists but the user asks for text decisions, proposed fixes, or a
  project summary, first summarize from text and only download media that is
  directly referenced by the text or needed to answer.
- If `collection_mode="fast"` gives enough evidence for a low-stakes status summary, stop there.

## Paging Budget

- For "fully today", "nothing missed", or exact quote requests, page until the requested date/window is complete or the facade reports no more matching messages.
- For broad project/chat orientation, start with one fast window. Add at most one broader follow-up window before summarizing unless the user asked for exhaustive coverage.
- For exhaustive requests, use an explicit budget before paging: usually stop
  after 5 pages or 500 messages unless the user asked to continue and the
  facade remains healthy.
- Stop paging on flood-wait, rate-limit, repeated empty pages, missing offsets,
  or tool errors. Report the last complete window and the reason paging stopped.
- Always report remaining `has_more_before`, `truncated`, or equivalent flags when they could affect the conclusion.

## Absolute Dates

When manually passing date ranges for relative dates like `today`, `yesterday`, or `this week`, use absolute dates in the user's local timezone. Prefer `telegram_read(day=...)` when available.

## Write Intent Examples

- "что ответить", "подготовь ответ", "draft" -> draft only.
- "покажи перед отправкой", "preview" -> non-sending preview only.
- "отправь: <exact text> <target>" -> resolve target, verify hard stops, then send.
- "send it" -> send only after an unchanged same-turn preview with the same
  target, reply id when relevant, and exact text.
- "ответь ему", "send him ok", fuzzy names, changed drafts, or old previews ->
  ask for a stable target/text or prepare a new preview.
