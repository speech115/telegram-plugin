# Media and voice

## Media

Use this when the user asks things like "что на картинке", "посмотри фото",
"опиши стикеры", or "какие картинки он присылал".

1. Read the relevant dialog window with `telegram_read`, `collect_dialog_context`, or `telegram_search`.
2. Collect message ids where `has_media=true` and `media_type` matches the request.
3. If `prepare_media_inspection_manifest` is available, use it to select explicit ids without unnecessary downloads.
4. Download selected messages with `download_media_batch` or `download_dialog_media`; use `download_media` for a single item when batch helpers are unavailable.
5. Open the downloaded local file with the image/video-aware viewer available in the host.
6. Answer from the actual file contents, not from Telegram metadata, captions, or manifest fields.

For broad ranges, list candidate ids first and inspect the most relevant batch unless the user explicitly wants every item. Batch media downloads in small groups, usually 5-10.

For video or animated stickers, inspect with a video-aware local tool when available. If only a still frame can be inspected, say that plainly.

## Voice

- Prefer built-in `voice_transcription` from reads or `transcribe_voice` for specific ids.
- Do not send voice notes to external APIs without explicit user approval.
- If a fast pass omitted voice and voice could change the answer, transcribe targeted ids only.

