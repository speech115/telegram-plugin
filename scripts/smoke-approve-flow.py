#!/usr/bin/env python3
"""Smoke: prepare -> reject send without approve -> approve -> send (Saved Messages)."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from telegram_control_plane.paths import MCP_REPO  # noqa: E402

sys.path.insert(0, str(MCP_REPO / "src"))

from telegram_mcp.mcp_http_client import call_tool_with_failover, load_env_file  # noqa: E402


async def main() -> int:
    load_env_file(Path("~/.telegram-mcp/launchd.env").expanduser())
    chat = "me"
    text = "[telegram-kit smoke] approve flow v3 — safe to delete"

    payload, _, _ = await call_tool_with_failover(
        tool_name="prepare_send_message",
        arguments={"chat": chat, "text": text, "parse_mode": "md"},
        timeout=30.0,
    )
    if not isinstance(payload, dict):
        print(json.dumps({"step": "prepare", "error": "unexpected payload"}, indent=2))
        return 1

    token = payload.get("confirmation_token")
    url = payload.get("human_approval_url")
    print(json.dumps({"step": "prepare", "ok": True, "human_approval_url": url}, indent=2, ensure_ascii=False))

    if not token:
        print(json.dumps({"step": "send_without_approve", "skipped": "no token"}))
        return 1

    blocked = False
    try:
        blocked_payload, _, _ = await call_tool_with_failover(
            tool_name="telegram_confirmed_send",
            arguments={
                "chat": payload["send_args_preview"]["chat"],
                "text": text,
                "confirmation_token": token,
                "parse_mode": "md",
            },
            timeout=30.0,
        )
        if isinstance(blocked_payload, str) and "human_approval_required" in blocked_payload:
            blocked = True
    except Exception as exc:
        blocked = "human_approval_required" in str(exc)

    print(
        json.dumps(
            {"step": "send_without_approve", "ok_blocked": blocked},
            indent=2,
            ensure_ascii=False,
        )
    )
    if not blocked:
        return 1

    import urllib.request

    if not url:
        print(json.dumps({"step": "approve", "error": "no approval url"}))
        return 1

    approve_url = str(url)
    if "action=approve" not in approve_url:
        approve_url += "&action=approve" if "?" in approve_url else "?action=approve"

    with urllib.request.urlopen(approve_url, timeout=10) as resp:
        html = resp.read().decode("utf-8", errors="replace")
    approved = "Одобрено" in html or "одобрено" in html.lower()
    print(json.dumps({"step": "approve_click", "ok": approved}, indent=2))

    sent, _, _ = await call_tool_with_failover(
        tool_name="telegram_confirmed_send",
        arguments={
            "chat": payload["send_args_preview"]["chat"],
            "text": text,
            "confirmation_token": token,
            "parse_mode": "md",
        },
        timeout=30.0,
    )
    send_ok = isinstance(sent, dict) and sent.get("text") == text
    if isinstance(sent, str) and "Error executing tool" in sent:
        print(json.dumps({"step": "send_after_approve", "ok": False, "payload": sent}, indent=2))
        return 1
    print(json.dumps({"step": "send_after_approve", "ok": send_ok, "payload": sent}, indent=2, ensure_ascii=False))
    return 0 if send_ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))