"""Minimal localhost Prometheus scrape endpoint for Telegram MCP."""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from .prometheus_registry import get_prometheus_registry

_server: ThreadingHTTPServer | None = None
_server_lock = threading.Lock()


class _MetricsHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        return

    def do_GET(self) -> None:  # noqa: N802
        if self.path in {"/metrics", "/metrics/"}:
            body = get_prometheus_registry().render().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path in {"/health", "/healthz", "/"}:
            body = b"ok\n"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(404)
        self.end_headers()


def start_metrics_server(*, host: str, port: int) -> None:
    global _server
    with _server_lock:
        if _server is not None:
            return
        httpd = ThreadingHTTPServer((host, port), _MetricsHandler)
        thread = threading.Thread(
            target=httpd.serve_forever,
            name="telegram-mcp-metrics",
            daemon=True,
        )
        thread.start()
        _server = httpd


def stop_metrics_server() -> None:
    global _server
    with _server_lock:
        if _server is None:
            return
        _server.shutdown()
        _server.server_close()
        _server = None