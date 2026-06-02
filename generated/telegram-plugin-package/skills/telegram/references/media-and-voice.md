# Media And Voice

## Media Inspection

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

## Artifact Lifecycle

Downloaded Telegram media is sensitive local evidence. Keep downloads in local
temporary storage by default. Do not move media to git, Drive, the vault, or
another durable/synced destination unless the user explicitly asks or the task
requires a retained artifact.

When media was downloaded only for one-time inspection, report the inspected
message ids and cleanup status when relevant. Prefer the workspace `safe-trash`
tool for cleanup when it is available and the file is no longer needed.

## Voice Notes

Use Telegram MCP/Telethon built-in transcription through `voice_transcription` from reads or `transcribe_voice`. Do not download Telegram voice notes and run local CPU Whisper by default.
Do not upload Telegram voice notes or media to external transcription, vision, or
file-processing services without explicit user approval.

For exact quotes, "выпиши", "что именно он сказал", or thin text plus voice notes, transcribe the relevant voice messages before answering.

If a fast first pass omitted voice transcripts and voice could affect the answer, make a targeted second call for the needed message ids instead of rereading a broad window.
