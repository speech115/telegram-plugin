from __future__ import annotations

import argparse
import asyncio
import json
import re
import sqlite3
import subprocess
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_CHAT_ID = -1003717342967
DEFAULT_ENV_FILE = Path.home() / ".telegram-mcp" / "launchd.env"
DEFAULT_RUNTIME_ROOT = Path("/Users/sereja/Projects/runtime/telegram-music-autoclean")
DEFAULT_SESSION = DEFAULT_RUNTIME_ROOT / "session" / "music_autoclean"
DEFAULT_STATE_DIR = DEFAULT_RUNTIME_ROOT / "state"
YOUTUBE_ID_RE = re.compile(r"(?<![A-Za-z0-9_-])([A-Za-z0-9_-]{11})(?![A-Za-z0-9_-])")
YOUTUBE_URL_RE = re.compile(
    r"(?:youtube\.com/watch\?v=|youtu\.be/)([A-Za-z0-9_-]{11})"
)


@dataclass(frozen=True)
class AudioMetadata:
    duration: int | None = None
    title: str | None = None
    performer: str | None = None
    voice: bool = False


@dataclass(frozen=True)
class CodeEntity:
    kind: str
    offset: int
    length: int
    url: str | None = None


@dataclass(frozen=True)
class MusicMessage:
    message_id: int
    text: str
    media_type: str | None
    mime_type: str | None
    file_name: str | None
    audio: AudioMetadata
    thumb_count: int
    entities: tuple[CodeEntity, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class Classification:
    action: str
    reasons: tuple[str, ...]
    youtube_ids: tuple[str, ...] = ()
    expected_caption: str | None = None


@dataclass(frozen=True)
class ProcessedTrack:
    source_msg_id: int
    cleaned_msg_id: int
    display: str
    youtube_id: str
    duration: int
    covered_audio_path: str


@dataclass(frozen=True)
class CandidateJob:
    raw: Any
    message: MusicMessage
    classification: Classification


def expected_caption(audio: AudioMetadata) -> str | None:
    if not audio.performer or not audio.title:
        return None
    return f"{audio.performer} - {audio.title}"


def has_full_code_entity(message: MusicMessage) -> bool:
    text_len = len(message.text or "")
    return any(
        entity.kind == "MessageEntityCode"
        and entity.offset == 0
        and entity.length == text_len
        for entity in message.entities
    )


def youtube_ids_from_message(message: MusicMessage) -> tuple[str, ...]:
    ids: list[str] = []
    for entity in message.entities:
        if entity.url:
            ids.extend(YOUTUBE_URL_RE.findall(entity.url))
    ids.extend(YOUTUBE_URL_RE.findall(message.text or ""))
    if message.file_name:
        ids.extend(YOUTUBE_ID_RE.findall(message.file_name))
    seen: set[str] = set()
    unique: list[str] = []
    for video_id in ids:
        if video_id not in seen:
            seen.add(video_id)
            unique.append(video_id)
    return tuple(unique)


def classify_music_message(
    message: MusicMessage,
    *,
    ledger_status: str | None = None,
) -> Classification:
    if ledger_status in {"done", "quarantine", "processing"}:
        return Classification(
            action="ignore_ledger",
            reasons=(f"ledger_status={ledger_status}",),
        )

    if message.media_type != "audio":
        return Classification(action="ignore_non_audio", reasons=("not_audio",))
    if message.audio.voice:
        return Classification(action="quarantine", reasons=("voice_audio",))
    if not message.audio.title or not message.audio.performer:
        return Classification(
            action="quarantine",
            reasons=("missing_title_or_performer",),
        )
    if not message.audio.duration or message.audio.duration <= 0:
        return Classification(action="quarantine", reasons=("missing_duration",))

    caption = expected_caption(message.audio)
    is_clean = (
        caption == message.text
        and has_full_code_entity(message)
        and message.thumb_count > 0
    )
    if is_clean:
        return Classification(
            action="ignore_clean_post",
            reasons=("caption_code_entity", "has_thumbnail", "metadata_matches"),
            expected_caption=caption,
        )

    video_ids = youtube_ids_from_message(message)
    if not video_ids:
        return Classification(
            action="quarantine",
            reasons=("no_youtube_provenance",),
            expected_caption=caption,
        )

    return Classification(
        action="candidate_process",
        reasons=("has_youtube_provenance",),
        youtube_ids=video_ids,
        expected_caption=caption,
    )


class Ledger:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.execute(
            """
            create table if not exists messages (
                chat_id integer not null,
                source_msg_id integer not null,
                cleaned_msg_id integer,
                status text not null,
                updated_at text default current_timestamp,
                detail_json text not null default '{}',
                primary key (chat_id, source_msg_id)
            )
            """
        )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def status_for(self, chat_id: int, message_id: int) -> str | None:
        row = self.conn.execute(
            "select status from messages where chat_id = ? and source_msg_id = ?",
            (chat_id, message_id),
        ).fetchone()
        return row[0] if row else None

    def record_dry_run(
        self,
        *,
        chat_id: int,
        message_id: int,
        status: str,
        detail: dict[str, Any],
    ) -> None:
        self.conn.execute(
            """
            insert into messages (chat_id, source_msg_id, status, detail_json)
            values (?, ?, ?, ?)
            on conflict(chat_id, source_msg_id) do update set
                status = excluded.status,
                updated_at = current_timestamp,
                detail_json = excluded.detail_json
            """,
            (chat_id, message_id, status, json.dumps(detail, ensure_ascii=False)),
        )
        self.conn.commit()

    def record_status(
        self,
        *,
        chat_id: int,
        message_id: int,
        status: str,
        detail: dict[str, Any],
        cleaned_msg_id: int | None = None,
    ) -> None:
        self.conn.execute(
            """
            insert into messages (
                chat_id, source_msg_id, cleaned_msg_id, status, detail_json
            )
            values (?, ?, ?, ?, ?)
            on conflict(chat_id, source_msg_id) do update set
                cleaned_msg_id = excluded.cleaned_msg_id,
                status = excluded.status,
                updated_at = current_timestamp,
                detail_json = excluded.detail_json
            """,
            (
                chat_id,
                message_id,
                cleaned_msg_id,
                status,
                json.dumps(detail, ensure_ascii=False),
            ),
        )
        self.conn.commit()


def load_env_file(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Dry-run Telegram music channel autoclean classifier"
    )
    parser.add_argument("--chat", type=int, default=DEFAULT_CHAT_ID)
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
    parser.add_argument("--session", type=Path, default=DEFAULT_SESSION)
    parser.add_argument("--state-dir", type=Path, default=DEFAULT_STATE_DIR)
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--max-process",
        type=int,
        default=3,
        help="Maximum candidate messages to process per apply run",
    )
    parser.add_argument(
        "--record-dry-run",
        action="store_true",
        help="Persist candidate/quarantine dry-run decisions to the local ledger",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Upload verified clean copies and delete verified source messages.",
    )
    parser.add_argument(
        "--i-understand-this-deletes-source",
        action="store_true",
        help="Future write-mode gate. Dry-run ignores it.",
    )
    return parser.parse_args(argv)


def entity_to_code_entity(entity: Any, text: str) -> CodeEntity:
    return CodeEntity(
        kind=type(entity).__name__,
        offset=int(getattr(entity, "offset", 0) or 0),
        length=int(getattr(entity, "length", 0) or 0),
        url=getattr(entity, "url", None),
    )


def raw_to_music_message(raw: Any) -> MusicMessage:
    from telethon.tl.types import DocumentAttributeAudio, DocumentAttributeFilename

    audio = AudioMetadata()
    file_name = None
    document = getattr(raw, "document", None)
    if document:
        for attr in getattr(document, "attributes", []) or []:
            if isinstance(attr, DocumentAttributeAudio):
                audio = AudioMetadata(
                    duration=getattr(attr, "duration", None),
                    title=getattr(attr, "title", None),
                    performer=getattr(attr, "performer", None),
                    voice=bool(getattr(attr, "voice", False)),
                )
            elif isinstance(attr, DocumentAttributeFilename):
                file_name = getattr(attr, "file_name", None)
    media_type = "audio" if getattr(raw, "audio", None) else None
    if media_type is None and getattr(raw, "media", None):
        media_type = type(raw.media).__name__
    text = raw.message or ""
    return MusicMessage(
        message_id=raw.id,
        text=text,
        media_type=media_type,
        mime_type=getattr(document, "mime_type", None) if document else None,
        file_name=file_name,
        audio=audio,
        thumb_count=len(getattr(document, "thumbs", []) or []) if document else 0,
        entities=tuple(
            entity_to_code_entity(entity, text)
            for entity in (getattr(raw, "entities", None) or [])
        ),
    )


async def open_client(args: argparse.Namespace) -> Any:
    from telethon import TelegramClient

    env = load_env_file(args.env_file)
    client = TelegramClient(
        str(args.session),
        int(env["TELEGRAM_API_ID"]),
        env["TELEGRAM_API_HASH"],
    )
    await client.connect()
    if not await client.is_user_authorized():
        await client.disconnect()
        raise RuntimeError("Telegram session is not authorized")
    return client


async def fetch_messages(args: argparse.Namespace) -> list[MusicMessage]:
    client = await open_client(args)
    entity = await client.get_entity(args.chat)
    raw_messages = await client.get_messages(entity, limit=args.limit)
    messages = [raw_to_music_message(raw) for raw in raw_messages]
    await client.disconnect()
    return messages


def safe_file_stem(text: str) -> str:
    text = re.sub(r'[/:\\?%*|"<>]', " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:180] or "track"


def run_json(command: list[str], *, timeout: int = 60) -> dict[str, Any]:
    raw = subprocess.check_output(
        command,
        text=True,
        stderr=subprocess.STDOUT,
        timeout=timeout,
    )
    return json.loads(raw.splitlines()[-1])


def youtube_metadata(video_id: str) -> dict[str, Any]:
    return run_json(
        [
            "yt-dlp",
            "--dump-json",
            "--no-warnings",
            f"https://www.youtube.com/watch?v={video_id}",
        ],
        timeout=60,
    )


def best_thumbnail_url(metadata: dict[str, Any], video_id: str) -> str:
    thumbnails = metadata.get("thumbnails") or []
    if thumbnails:
        thumbnails = sorted(
            thumbnails,
            key=lambda item: (item.get("width") or 0) * (item.get("height") or 0),
            reverse=True,
        )
        url = thumbnails[0].get("url")
        if url:
            return str(url)
    if metadata.get("thumbnail"):
        return str(metadata["thumbnail"])
    return f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"


def download_thumbnail(video_id: str, url: str, dest: Path) -> str:
    candidates = [
        url,
        f"https://i.ytimg.com/vi/{video_id}/maxresdefault.jpg",
        f"https://i.ytimg.com/vi/{video_id}/sddefault.jpg",
        f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
    ]
    seen: set[str] = set()
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        try:
            request = urllib.request.Request(
                candidate,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            with urllib.request.urlopen(request, timeout=20) as response:
                data = response.read()
            if len(data) < 5_000:
                continue
            dest.write_bytes(data)
            return candidate
        except Exception:
            continue
    raise RuntimeError(f"no usable thumbnail for YouTube id {video_id}")


def prepare_cover_files(
    *,
    state_dir: Path,
    source_path: Path,
    message: MusicMessage,
    video_id: str,
    metadata: dict[str, Any],
) -> tuple[Path, Path]:
    display = expected_caption(message.audio)
    if not display or not message.audio.title or not message.audio.performer:
        raise RuntimeError("missing display metadata")
    work_dir = state_dir / "work" / str(message.message_id)
    work_dir.mkdir(parents=True, exist_ok=True)
    raw_cover = work_dir / "cover.raw"
    cover = work_dir / "cover.jpg"
    upload_thumb = work_dir / "thumb.jpg"
    dest_audio = work_dir / f"{safe_file_stem(display)}.m4a"

    used_thumbnail = download_thumbnail(
        video_id,
        best_thumbnail_url(metadata, video_id),
        raw_cover,
    )
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(raw_cover),
            "-vf",
            "scale=640:640:force_original_aspect_ratio=increase,crop=640:640",
            "-frames:v",
            "1",
            "-q:v",
            "3",
            str(cover),
        ],
        check=True,
    )
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(cover),
            "-vf",
            "scale=320:320:force_original_aspect_ratio=increase,crop=320:320",
            "-frames:v",
            "1",
            "-q:v",
            "5",
            str(upload_thumb),
        ],
        check=True,
    )
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(source_path),
            "-i",
            str(cover),
            "-map",
            "0:a:0",
            "-map",
            "1:v:0",
            "-c:a",
            "copy",
            "-c:v",
            "mjpeg",
            "-disposition:v:0",
            "attached_pic",
            "-metadata",
            f"artist={message.audio.performer}",
            "-metadata",
            f"title={message.audio.title}",
            "-metadata",
            "album=",
            "-metadata",
            "comment=",
            "-metadata",
            "description=",
            str(dest_audio),
        ],
        check=True,
    )
    (work_dir / "thumbnail_used.txt").write_text(used_thumbnail, encoding="utf-8")
    return dest_audio, upload_thumb


def markdown_code(text: str) -> str:
    return "`" + text.replace("`", "") + "`"


def verify_clean_message(sent: Any, source: MusicMessage) -> MusicMessage:
    clean = raw_to_music_message(sent)
    expected = expected_caption(source.audio)
    if clean.text != expected:
        raise RuntimeError(f"uploaded caption mismatch: {clean.text!r} != {expected!r}")
    if not has_full_code_entity(clean):
        raise RuntimeError("uploaded caption is not full MessageEntityCode")
    if clean.thumb_count <= 0:
        raise RuntimeError("uploaded message has no Telegram thumbnail")
    if clean.audio.duration != source.audio.duration:
        raise RuntimeError(
            f"uploaded duration mismatch: {clean.audio.duration} != {source.audio.duration}"
        )
    if clean.audio.title != source.audio.title:
        raise RuntimeError(
            f"uploaded title mismatch: {clean.audio.title!r} != {source.audio.title!r}"
        )
    if clean.audio.performer != source.audio.performer:
        raise RuntimeError(
            "uploaded performer mismatch: "
            f"{clean.audio.performer!r} != {source.audio.performer!r}"
        )
    return clean


def candidate_jobs_in_playlist_order(
    *,
    raw_messages: list[Any],
    ledger: Ledger,
    chat_id: int,
    max_process: int,
) -> list[CandidateJob]:
    jobs: list[CandidateJob] = []
    for raw in raw_messages:
        message = raw_to_music_message(raw)
        ledger_status = ledger.status_for(chat_id, message.message_id)
        classification = classify_music_message(
            message,
            ledger_status=ledger_status,
        )
        if classification.action == "candidate_process":
            jobs.append(
                CandidateJob(
                    raw=raw,
                    message=message,
                    classification=classification,
                )
            )
    return sorted(jobs, key=lambda job: job.message.message_id)[:max_process]


async def process_candidate(
    *,
    client: Any,
    entity: Any,
    raw: Any,
    message: MusicMessage,
    classification: Classification,
    args: argparse.Namespace,
) -> ProcessedTrack:
    from telethon.tl.types import DocumentAttributeAudio, DocumentAttributeFilename

    if not classification.youtube_ids:
        raise RuntimeError("candidate has no YouTube id")
    display = classification.expected_caption
    if not display:
        raise RuntimeError("candidate has no expected caption")

    video_id = classification.youtube_ids[0]
    source_dir = args.state_dir / "sources" / str(message.message_id)
    source_dir.mkdir(parents=True, exist_ok=True)
    source_name = message.file_name or f"{message.message_id}.m4a"
    source_path = source_dir / safe_file_stem(source_name)
    if source_path.suffix.lower() != ".m4a":
        source_path = source_path.with_suffix(".m4a")
    await client.download_media(raw, file=str(source_path))
    metadata = youtube_metadata(video_id)
    youtube_duration = metadata.get("duration")
    if isinstance(youtube_duration, int | float) and message.audio.duration:
        if abs(float(youtube_duration) - float(message.audio.duration)) > 3:
            raise RuntimeError(
                "YouTube duration mismatch: "
                f"{youtube_duration} != {message.audio.duration}"
            )

    covered_audio, upload_thumb = prepare_cover_files(
        state_dir=args.state_dir,
        source_path=source_path,
        message=message,
        video_id=video_id,
        metadata=metadata,
    )
    attrs = [
        DocumentAttributeAudio(
            duration=message.audio.duration or 1,
            title=message.audio.title,
            performer=message.audio.performer,
        ),
        DocumentAttributeFilename(file_name=covered_audio.name),
    ]
    sent = await client.send_file(
        entity,
        str(covered_audio),
        caption=markdown_code(display),
        parse_mode="md",
        attributes=attrs,
        thumb=str(upload_thumb),
    )
    clean = verify_clean_message(sent, message)
    await client.delete_messages(entity, [message.message_id], revoke=True)
    return ProcessedTrack(
        source_msg_id=message.message_id,
        cleaned_msg_id=clean.message_id,
        display=display,
        youtube_id=video_id,
        duration=message.audio.duration or 0,
        covered_audio_path=str(covered_audio),
    )


async def apply_candidates(args: argparse.Namespace, ledger: Ledger) -> dict[str, Any]:
    client = await open_client(args)
    processed: list[dict[str, Any]] = []
    quarantined: list[dict[str, Any]] = []
    try:
        entity = await client.get_entity(args.chat)
        raw_messages = await client.get_messages(entity, limit=args.limit)
        jobs = candidate_jobs_in_playlist_order(
            raw_messages=list(raw_messages),
            ledger=ledger,
            chat_id=args.chat,
            max_process=args.max_process,
        )
        for job in jobs:
            raw = job.raw
            message = job.message
            classification = job.classification
            base_detail = {
                "message_id": message.message_id,
                "youtube_ids": list(classification.youtube_ids),
                "expected_caption": classification.expected_caption,
                "title": message.audio.title,
                "performer": message.audio.performer,
                "duration": message.audio.duration,
                "file_name": message.file_name,
            }
            ledger.record_status(
                chat_id=args.chat,
                message_id=message.message_id,
                status="processing",
                detail=base_detail,
            )
            try:
                result = await process_candidate(
                    client=client,
                    entity=entity,
                    raw=raw,
                    message=message,
                    classification=classification,
                    args=args,
                )
            except Exception as exc:
                detail = base_detail | {"error": str(exc)}
                ledger.record_status(
                    chat_id=args.chat,
                    message_id=message.message_id,
                    status="quarantine",
                    detail=detail,
                )
                quarantined.append(detail)
                continue
            detail = base_detail | asdict(result)
            ledger.record_status(
                chat_id=args.chat,
                message_id=message.message_id,
                cleaned_msg_id=result.cleaned_msg_id,
                status="done",
                detail=detail,
            )
            processed.append(detail)
    finally:
        await client.disconnect()
    return {
        "status": "ok",
        "mode": "apply",
        "chat_id": args.chat,
        "ledger_path": str(args.state_dir / "ledger.sqlite3"),
        "processed_count": len(processed),
        "quarantine_count": len(quarantined),
        "processed": processed,
        "quarantined": quarantined,
    }


async def build_report(args: argparse.Namespace) -> dict[str, Any]:
    ledger_path = args.state_dir / "ledger.sqlite3"
    ledger = Ledger(ledger_path)
    if args.apply:
        try:
            if not args.i_understand_this_deletes_source:
                return {
                    "status": "fail",
                    "mode": "apply",
                    "error": "apply requires --i-understand-this-deletes-source",
                }
            return await apply_candidates(args, ledger)
        finally:
            ledger.close()
    try:
        messages = await fetch_messages(args)
        items: list[dict[str, Any]] = []
        counts: dict[str, int] = {}
        for message in messages:
            ledger_status = ledger.status_for(args.chat, message.message_id)
            classification = classify_music_message(
                message,
                ledger_status=ledger_status,
            )
            counts[classification.action] = counts.get(classification.action, 0) + 1
            item = {
                "message_id": message.message_id,
                "action": classification.action,
                "reasons": list(classification.reasons),
                "youtube_ids": list(classification.youtube_ids),
                "expected_caption": classification.expected_caption,
                "text": message.text,
                "file_name": message.file_name,
                "duration": message.audio.duration,
                "title": message.audio.title,
                "performer": message.audio.performer,
                "thumb_count": message.thumb_count,
                "entity_types": [entity.kind for entity in message.entities],
            }
            if args.record_dry_run and classification.action in {
                "candidate_process",
                "quarantine",
            }:
                ledger.record_dry_run(
                    chat_id=args.chat,
                    message_id=message.message_id,
                    status=f"dry_run_{classification.action}",
                    detail=item,
                )
            items.append(item)
    finally:
        ledger.close()

    return {
        "status": "ok",
        "mode": "dry_run",
        "chat_id": args.chat,
        "ledger_path": str(ledger_path),
        "counts": counts,
        "items": items,
    }


def render_text(report: dict[str, Any]) -> str:
    if report.get("status") != "ok":
        return f"status: {report.get('status')}\nerror: {report.get('error')}"
    lines = [
        f"status: {report['status']}",
        f"mode: {report['mode']}",
        f"chat_id: {report['chat_id']}",
        f"counts: {json.dumps(report['counts'], ensure_ascii=False, sort_keys=True)}",
    ]
    for item in report["items"]:
        lines.append(
            f"- {item['message_id']}: {item['action']} "
            f"({', '.join(item['reasons'])}) {item.get('expected_caption') or ''}"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = asyncio.run(build_report(args))
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(render_text(report))
    return 0 if report.get("status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
