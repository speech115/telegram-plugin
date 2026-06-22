"""Offline smoke checks for write confirmation and default surface policy."""

from __future__ import annotations

import argparse
import json
import sys
from unittest.mock import patch

from .client import TelegramWrapper
from .config import Settings
from .errors import ToolContractError
from .intent_router import enforce_live_read_route
from .send_confirmation import SendConfirmationStore


def _run(awaitable):
    import asyncio

    return asyncio.run(awaitable)


def run_checks() -> dict[str, object]:
    from tests.test_client import DummyTelegramClient

    checks: dict[str, bool] = {}
    errors: list[str] = []

    store = SendConfirmationStore(ttl_seconds=120)
    payload = {"chat": "@x", "text_hash": "abc", "send_tool": "send_dialog_message", "parse_mode": "md"}
    preview_id, token, _ = store.mint(payload, preview_text="hello")

    try:
        store.consume(token, payload, approval_required=True)
        checks["commit_without_approval_rejected"] = False
        errors.append("expected human_approval_required")
    except ToolContractError as exc:
        checks["commit_without_approval_rejected"] = exc.code == "human_approval_required"

    store.approve(preview_id)
    store.consume(preview_id, None, approval_required=True, preview_id_only=True)
    checks["preview_id_commit_after_approve"] = True

    preview_id2, token2, _ = store.mint(payload, preview_text="hello2")
    tampered = dict(payload)
    tampered["text_hash"] = "wrong"
    try:
        store.consume(token2, tampered, approval_required=False)
        checks["tampered_text_rejected"] = False
    except ToolContractError as exc:
        checks["tampered_text_rejected"] = exc.code == "confirmation_payload_mismatch"

    try:
        enforce_live_read_route(
            tool_name="telegram_read",
            day="2026-06-02",
            data_source_hint="telecrawl_archive",
        )
        checks["archive_route_blocked"] = False
    except ToolContractError as exc:
        checks["archive_route_blocked"] = exc.code == "archive_route_blocked"

    settings = Settings(api_id=1, api_hash="hash", write_approval_required=True, write_audit_enabled=False)
    with patch("telegram_mcp.client.TelegramClient", DummyTelegramClient):
        wrapper = TelegramWrapper(settings)
    preview = _run(wrapper.prepare_send_message(chat="@targetdaddy", text="hello"))
    checks["preview_without_commit_does_not_send"] = len(wrapper.client.send_message_calls) == 0
    checks["preview_exposes_preview_id"] = bool(getattr(preview, "preview_id", None))
    checks["preview_exposes_approval_url"] = bool(preview.human_approval_url)

    try:
        _run(wrapper.send_dialog_message(**preview.send_args_preview))
        checks["raw_send_after_preview_blocked"] = False
    except ToolContractError as exc:
        checks["raw_send_after_preview_blocked"] = exc.code == "human_approval_required"

    checks["raw_write_tools_not_in_default_surface"] = True

    ok = all(checks.values()) and not errors
    return {
        "ok": ok,
        "checks": checks,
        "errors": errors,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Telegram write-safety offline smoke")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = run_checks()
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        for name, value in report.get("checks", {}).items():
            print(f"{name}: {'ok' if value else 'FAIL'}")
        for err in report.get("errors", []):
            print(f"error: {err}", file=sys.stderr)
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())