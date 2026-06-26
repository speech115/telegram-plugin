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

    def _form_fields(self) -> dict[str, str]:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length).decode("utf-8") if length else ""
        return {
            key: values[0]
            for key, values in parse_qs(raw).items()
            if values
        }

    def _mutate(self, *, token: str, nonce: str, action: str) -> str:
        store = get_confirmation_store()
        record = store.get(token)
        if record is None:
            raise ToolContractError("invalid_confirmation_token", "confirmation token is unknown")
        if nonce != record.one_time_nonce:
            raise ToolContractError("invalid_confirmation_token", "approval nonce is invalid")
        if record.approval_state == "approved":
            return "<h1>Уже одобрено</h1><p class='meta'>Можно отправлять через telegram_confirmed_send.</p>"
        if record.approval_state == "used":
            return "<h1>Уже использовано</h1><p class='meta'>Этот токен уже был отправлен.</p>"
        if record.approval_state == "rejected":
            return "<h1>Уже отклонено</h1><p class='meta'>Создайте новое превью, если нужно отправить сообщение.</p>"
        if record.approval_state == "expired":
            raise ToolContractError("expired_confirmation_token", "confirmation token has expired")
        if action == "approve":
            store.approve(token)
            return "<h1>Одобрено</h1><p class='meta'>Можно отправлять через telegram_confirmed_send.</p>"
        if action == "reject":
            store.reject(token)
            return "<h1>Отклонено</h1><p class='meta'>Отправка заблокирована.</p>"
        raise ToolContractError("invalid_input", "unknown approval action")

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path not in {"/telegram/approve", "/telegram/approve/"}:
            self._send(404, "text/plain", b"not found\n")
            return
        fields = self._form_fields()
        token = fields.get("token") or ""
        nonce = fields.get("nonce") or ""
        action = fields.get("action") or ""
        try:
            inner = self._mutate(token=token, nonce=nonce, action=action)
            status = 200
        except ToolContractError as exc:
            inner = f"<h1>Ошибка</h1><p class='meta'>{html.escape(exc.message)}</p>"
            status = 400
        page_status, ctype, body = _page("Telegram approve", inner, status=status)
        self._send(page_status, ctype, body)

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
	  <form method="post" action="/telegram/approve">
	    <input type="hidden" name="token" value="{html.escape(token)}" />
	    <input type="hidden" name="nonce" value="{html.escape(record.one_time_nonce)}" />
	    <input type="hidden" name="action" value="approve" />
	    <button class="ok" type="submit">Одобрить</button>
	  </form>
	  <form method="post" action="/telegram/approve">
	    <input type="hidden" name="token" value="{html.escape(token)}" />
	    <input type="hidden" name="nonce" value="{html.escape(record.one_time_nonce)}" />
	    <input type="hidden" name="action" value="reject" />
	    <button class="no" type="submit">Отклонить</button>
	  </form>
	</div>
	<p class="meta">После одобрения агент может вызвать telegram_confirmed_send с тем же текстом.</p>
	"""

        status, ctype, body = _page("Telegram approve", inner)
        self._send(status, ctype, body)


def start_approval_server(*, host: str, port: int) -> None:
    global _server
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("approval server host must be loopback")
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
