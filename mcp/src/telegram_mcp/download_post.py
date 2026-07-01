"""Прямое скачивание медиа из поста по t.me-ссылке.

Минует MCP HTTP (у MCP-инструмента download_media жёсткий 120с-таймаут, которого
не хватает для больших видео). Подключается отдельным Telethon-клиентом на
снимке сессии аккаунта, поэтому не конфликтует с file-lock запущенного сервера
(Telegram допускает несколько подключений на один auth key).
"""

from __future__ import annotations

import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from telethon import TelegramClient
from telethon.sessions import StringSession

from .mcp_http_client import ACCOUNT_ENDPOINTS, McpCliError, load_env_file
from .telemetry import record_telemetry

DEFAULT_DEST_DIR = Path.home() / "Downloads"

# t.me/c/<internal>/<msg>, t.me/c/<internal>/<thread>/<msg>,
# t.me/<username>/<msg>, t.me/<username>/<thread>/<msg> (с/без https, с/без @)
_LINK_RE = re.compile(
    r"""(?:https?://)?t\.me/
        (?:
            c/(?P<internal>\d+)/(?P<c_ids>\d+(?:/\d+)?)        # приватный канал
          | (?P<username>[A-Za-z][A-Za-z0-9_]{3,31})/(?P<u_ids>\d+(?:/\d+)?)  # публичный
        )
    """,
    re.VERBOSE,
)


@dataclass
class ParsedLink:
    chat: str | int      # int peer id для приватного канала, "@username" для публичного
    message_id: int
    label: str           # короткий слаг для имени файла


def parse_post_link(link: str) -> ParsedLink:
    """Разобрать t.me-ссылку на пост в (chat_ref, message_id).

    Для приватного канала chat — int peer id (-100<internal>): Telethon резолвит
    его через кэш сессии. Строку с числом он ошибочно ищет в контактах.
    """
    m = _LINK_RE.search(link.strip())
    if not m:
        raise McpCliError(
            f"не похоже на ссылку t.me на пост: {link!r} "
            "(ожидаю t.me/c/<id>/<msg> или t.me/<username>/<msg>)"
        )
    if m.group("internal"):
        internal = m.group("internal")
        msg_id = int(m.group("c_ids").split("/")[-1])
        return ParsedLink(chat=int(f"-100{internal}"), message_id=msg_id, label=f"c{internal}")
    username = m.group("username")
    msg_id = int(m.group("u_ids").split("/")[-1])
    return ParsedLink(chat=f"@{username}", message_id=msg_id, label=username)


def _account_env_file(account: str) -> Path:
    config = ACCOUNT_ENDPOINTS.get(account)
    if not config:
        known = ", ".join(sorted(ACCOUNT_ENDPOINTS))
        raise McpCliError(f"неизвестный аккаунт {account!r}; доступны: {known}")
    _port, env_file = config
    return Path(env_file).expanduser()


def _ext_from_message(msg) -> str:
    doc = getattr(getattr(msg, "media", None), "document", None)
    if doc is not None:
        for attr in getattr(doc, "attributes", []) or []:
            name = getattr(attr, "file_name", None)
            if name and "." in name:
                return Path(name).suffix
        mime = getattr(doc, "mime_type", "") or ""
        if mime == "video/mp4":
            return ".mp4"
        if "/" in mime:
            return "." + mime.split("/")[-1].split(";")[0]
    if getattr(getattr(msg, "media", None), "photo", None) is not None:
        return ".jpg"
    return ".bin"


def _telethon_media_kind(msg) -> str | None:
    media = getattr(msg, "media", None)
    if media is None:
        return None
    if getattr(media, "photo", None) is not None:
        return "photo"
    doc = getattr(media, "document", None)
    if doc is None:
        return None
    mime = getattr(doc, "mime_type", "") or ""
    if mime.startswith("video/"):
        return "video"
    if mime.startswith("audio/"):
        return "audio"
    return "document"


def _telethon_media_size_bytes(msg) -> int | None:
    media = getattr(msg, "media", None)
    if media is None:
        return None
    photo = getattr(media, "photo", None)
    if photo is not None:
        sizes = getattr(photo, "sizes", None) or []
        if not sizes:
            return None
        return max(getattr(s, "size", 0) for s in sizes)
    doc = getattr(media, "document", None)
    if doc is not None:
        return getattr(doc, "size", None)
    return None


def _make_progress():
    last = {"pct": -5}

    def cb(done: int, total: int) -> None:
        pct = (done / total * 100) if total else 0
        if pct - last["pct"] >= 5 or done == total:
            last["pct"] = pct
            mb = done / 1024 / 1024
            tmb = (total / 1024 / 1024) if total else 0
            print(f"PROGRESS {mb:.0f}/{tmb:.0f}MB {pct:.1f}%", flush=True)

    return cb


def _snapshot_session(session_file: Path) -> Path:
    """Копия SQLite-сессии (с -wal/-shm) во временный файл.

    Простое копирование файла, а не sqlite .backup(): backup-снапшот ловит
    TypeNotFoundError при чтении ответов, файловая копия работает стабильно.
    """
    tmp_dir = Path(tempfile.mkdtemp(prefix="tg-dl-"))
    tmp = tmp_dir / "session.session"
    shutil.copy2(session_file, tmp)
    for suffix in ("-wal", "-shm"):
        sidecar = session_file.with_name(session_file.name + suffix)
        if sidecar.exists():
            shutil.copy2(sidecar, tmp_dir / (tmp.name + suffix))
    return tmp


async def download_post(
    *,
    link: str,
    account: str = "main",
    dest_dir: Path | None = None,
    quiet: bool = False,
) -> dict[str, object]:
    parsed = parse_post_link(link)
    env_file = _account_env_file(account)
    if env_file.exists():
        load_env_file(env_file)

    api_id = os.environ.get("TELEGRAM_API_ID", "").strip()
    api_hash = os.environ.get("TELEGRAM_API_HASH", "").strip()
    if not api_id or not api_hash:
        raise McpCliError(f"нет TELEGRAM_API_ID/API_HASH для аккаунта {account!r} ({env_file})")

    session_string = os.environ.get("TELEGRAM_SESSION_STRING", "").strip()
    tmp_session: Path | None = None
    if session_string:
        session = StringSession(session_string)
    else:
        session_file = env_file.parent / "session.session"
        if not session_file.exists():
            raise McpCliError(f"не найден файл сессии: {session_file}")
        tmp_session = _snapshot_session(session_file)
        session = str(tmp_session.with_suffix(""))  # Telethon добавит .session

    dest_dir = (dest_dir or DEFAULT_DEST_DIR).expanduser()
    dest_dir.mkdir(parents=True, exist_ok=True)

    client = TelegramClient(session, int(api_id), api_hash)
    try:
        await client.connect()
        if not await client.is_user_authorized():
            raise McpCliError(f"сессия аккаунта {account!r} не авторизована")
        entity = await client.get_entity(parsed.chat)
        msg = await client.get_messages(entity, ids=parsed.message_id)
        if not msg or not getattr(msg, "media", None):
            raise McpCliError(
                f"в сообщении {parsed.message_id} нет медиа "
                f"(чат {parsed.chat}, аккаунт {account})"
            )
        out = dest_dir / f"{parsed.label}_{parsed.message_id}{_ext_from_message(msg)}"

        from . import tdlib_download  # lazy: keeps pytdbot fully optional at module load time

        tdlib_enabled = os.environ.get("TELEGRAM_TDLIB_ENABLED", "false").strip().lower() == "true"
        threshold_mb = float(os.environ.get("TELEGRAM_TDLIB_DOWNLOAD_THRESHOLD_MB", "20"))
        route_to_tdlib = tdlib_download.should_route_to_tdlib(
            account=account,
            tdlib_enabled=tdlib_enabled,
            content_kind=_telethon_media_kind(msg),
            media_size_bytes=_telethon_media_size_bytes(msg),
            threshold_mb=threshold_mb,
        )

        tdlib_backend_used = False
        fallback_reason: str | None = None
        saved: str | None = None

        if route_to_tdlib:
            session_dir = Path(
                os.environ.get("TELEGRAM_TDLIB_SESSION_DIR", "~/.telegram-mcp-tdlib/main")
            ).expanduser()
            try:
                tdlib_path = await tdlib_download.download_via_tdlib(link=link, session_dir=session_dir)
                shutil.copy2(tdlib_path, out)
                saved = str(out)
                tdlib_backend_used = True
            except Exception as exc:  # noqa: BLE001 - any TDLib failure falls back to Telethon
                fallback_reason = str(exc)

        if saved is None:
            progress = None if quiet else _make_progress()
            saved = await client.download_media(msg, file=str(out), progress_callback=progress)

        record_telemetry(
            "download_post_backend",
            backend="tdlib" if tdlib_backend_used else "telethon",
            account=account,
            route_attempted=route_to_tdlib,
            fallback_reason=fallback_reason,
        )
    finally:
        await client.disconnect()
        if tmp_session is not None:
            try:
                for p in tmp_session.parent.iterdir():
                    p.unlink(missing_ok=True)
                tmp_session.parent.rmdir()
            except OSError:
                pass

    saved_path = Path(saved) if saved else out
    return {
        "chat": parsed.chat,
        "message_id": parsed.message_id,
        "account": account,
        "path": str(saved_path),
        "size_bytes": saved_path.stat().st_size if saved_path.exists() else None,
    }
