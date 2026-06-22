"""Localhost human approval UI for pending Telegram sends."""

from __future__ import annotations

import html
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from .errors import ToolContractError
from .send_confirmation import get_confirmation_store

_server: ThreadingHTTPServer | None = None
_server_lock = threading.Lock()


def _page(title: str, body: str, *, status: int = 200) -> tuple[int, str, bytes]:
    doc = f"""<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{html.escape(title)}</title>
  <style>
    body {{ font-family: -apple-system, sans-serif; background: #0f1419; color: #e8edf4; margin: 2rem; }}
    .card {{ max-width: 640px; background: #1a2332; border-radius: 12px; padding: 1.25rem; border: 1px solid #243044; }}
    h1 {{ font-size: 1.25rem; margin: 0 0 1rem; }}
    pre {{ white-space: pre-wrap; background: #243044; padding: 1rem; border-radius: 8px; }}
    .meta {{ color: #8b9cb3; font-size: 0.9rem; margin-bottom: 1rem; }}
    .actions {{ display: flex; gap: 0.75rem; margin-top: 1rem; }}
    a, button {{ display: inline-block; padding: 0.6rem 1.1rem; border-radius: 8px; text-decoration: none; font-weight: 600; border: none; cursor: pointer; }}
    .ok {{ background: #3dd68c; color: #0f1419; }}
    .no {{ background: #e85d5d; color: #fff; }}
  </style>
</head>
<body><div class="card">{body}</div></body>
</html>"""
    return status, "text/html; charset=utf-8", doc.encode("utf-8")


class _ApprovalHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        return

    def _send(self, status: int, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path not in {"/telegram/approve", "/telegram/approve/"}:
            self._send(404, "text/plain", b"not found\n")
            return

        token = (parse_qs(parsed.query).get("token") or [None])[0]
        if not token:
            status, ctype, body = _page(
                "Telegram approve",
                "<h1>Нет токена</h1><p class='meta'>Откройте ссылку из превью отправки.</p>",
                status=400,
            )
            self._send(status, ctype, body)
            return

        store = get_confirmation_store()
        record = store.get(token)
        if record is None:
            status, ctype, body = _page(
                "Не найдено",
                "<h1>Превью не найдено</h1><p class='meta'>Токен устарел или уже использован.</p>",
                status=404,
            )
            self._send(status, ctype, body)
            return

        payload = record.payload
        chat = html.escape(str(payload.get("chat", "?")))
        tool = html.escape(str(payload.get("send_tool", "?")))
        state = html.escape(record.approval_state)
        text = html.escape(record.preview_text)
        msg_id = payload.get("message_id")
        reply_line = (
            f"<p class='meta'>Ответ на сообщение: <strong>{html.escape(str(msg_id))}</strong></p>"
            if msg_id is not None
            else ""
        )

        if record.approval_state in {"approved", "used"}:
            inner = f"<h1>Уже одобрено</h1><p class='meta'>Статус: {state}</p>"
        elif record.approval_state == "rejected":
            inner = f"<h1>Отклонено</h1><p class='meta'>Статус: {state}</p>"
        elif record.approval_state == "expired":
            inner = "<h1>Истекло</h1><p class='meta'>Создайте новое превью.</p>"
        else:
            inner = f"""
<h1>Отправить в Telegram?</h1>
<p class='meta'>Кому: <strong>{chat}</strong> · инструмент: {tool} · статус: {state}</p>
{reply_line}
<pre>{text}</pre>
<div class="actions">
  <a class="ok" href="/telegram/approve?token={html.escape(token)}&amp;action=approve">Одобрить</a>
  <a class="no" href="/telegram/approve?token={html.escape(token)}&amp;action=reject">Отклонить</a>
</div>
<p class="meta">После одобрения агент может вызвать telegram_confirmed_send с тем же текстом.</p>
"""

        action = (parse_qs(parsed.query).get("action") or [None])[0]
        if action == "approve" and record.approval_state == "pending":
            try:
                store.approve(token)
                inner = "<h1>Одобрено</h1><p class='meta'>Можно отправлять через telegram_confirmed_send.</p>" + inner
            except ToolContractError as exc:
                inner = f"<h1>Ошибка</h1><p class='meta'>{html.escape(exc.message)}</p>"
        elif action == "reject" and record.approval_state == "pending":
            store.reject(token)
            inner = "<h1>Отклонено</h1><p class='meta'>Отправка заблокирована.</p>"

        status, ctype, body = _page("Telegram approve", inner)
        self._send(status, ctype, body)


def start_approval_server(*, host: str, port: int) -> None:
    global _server
    with _server_lock:
        if _server is not None:
            return
        httpd = ThreadingHTTPServer((host, port), _ApprovalHandler)
        thread = threading.Thread(
            target=httpd.serve_forever,
            name="telegram-mcp-approval",
            daemon=True,
        )
        thread.start()
        _server = httpd


def stop_approval_server() -> None:
    global _server
    with _server_lock:
        if _server is None:
            return
        _server.shutdown()
        _server.server_close()
        _server = None