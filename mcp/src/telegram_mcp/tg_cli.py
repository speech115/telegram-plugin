"""Unified `tg` CLI: fast live reads and search via local MCP HTTP (no plugin bootstrap)."""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from datetime import date

from .metadata_tools_spec import (
    COUNT_SPECS_BY_CLI,
    LIST_SPECS_BY_CLI,
    METADATA_COUNT_SPECS,
    METADATA_LIST_SPECS,
    MetadataCountSpec,
)
from .mcp_http_client import ACCOUNT_ENDPOINTS, McpCliError, call_tool_with_failover
from .telemetry import record_telemetry, telemetry_fields_from_result


def _payload_is_tool_error(payload: object | None) -> bool:
    if isinstance(payload, str):
        lower = payload.lower()
        return "unknown tool" in lower or "error executing tool " in lower
    if isinstance(payload, dict):
        return _payload_is_tool_error(payload.get("error") or payload.get("message"))
    return False


def _wrap_ok(
    *,
    command: str,
    endpoint: str,
    endpoint_port: int | None,
    elapsed_seconds: float,
    payload: object | None,
    intent: str,
) -> dict[str, object]:
    data_source = None
    if isinstance(payload, dict):
        data_source = payload.get("data_source")
    if _payload_is_tool_error(payload):
        wrapped = {
            "ok": False,
            "command": command,
            "intent": intent,
            "data_source": data_source or "live_telegram",
            "endpoint": endpoint,
            "endpoint_port": endpoint_port,
            "elapsed_seconds": elapsed_seconds,
            "error": "telegram_tool_error",
            "message": "Live Telegram tool returned an error payload.",
        }
        if isinstance(payload, dict):
            wrapped["tool_error_payload"] = payload
        elif isinstance(payload, str):
            wrapped["tool_error_payload"] = payload[:2000]
        return wrapped
    return {
        "ok": True,
        "command": command,
        "intent": intent,
        "data_source": data_source or "live_telegram",
        "endpoint": endpoint,
        "endpoint_port": endpoint_port,
        "elapsed_seconds": elapsed_seconds,
        "payload": payload,
    }


def _wrap_err(*, command: str, exc: Exception) -> dict[str, object]:
    return {
        "ok": False,
        "command": command,
        "error_type": type(exc).__name__,
        "error": str(exc),
    }


CHAT_RE = re.compile(r"(?P<chat>@[A-Za-z0-9_]{5,}|tg://dialog/[^\s]+|-100\d{6,}|\bme\b)", re.IGNORECASE)
COUNT_POSTS_RE = re.compile(
    r"(сколько|count|how many|total).{0,80}(пост|posts?|messages?|сообщен)",
    re.IGNORECASE,
)
COUNT_RE = re.compile(r"(сколько|count|how many|total)", re.IGNORECASE)
LIST_RE = re.compile(r"(list|show|дай|покажи|выведи|список)", re.IGNORECASE)
LATEST_RE = re.compile(r"(latest|last|последн)", re.IGNORECASE)
INFO_RE = re.compile(r"(info|metadata|about|инфо|метадан|о канале|о чате)", re.IGNORECASE)
MESSAGE_ID_RE = re.compile(r"(?:message|msg|сообщени[ея]|пост)\s*(?:id)?\s*#?(?P<message_id>\d+)", re.IGNORECASE)
SEARCH_RE = re.compile(r"(найди|search|искать|поиск)", re.IGNORECASE)
TODAY_RE = re.compile(r"(сегодня|today|что нового|прочитай)", re.IGNORECASE)


def _extract_chat(text: str) -> str | None:
    match = CHAT_RE.search(text)
    return match.group("chat") if match else None


def _count_spec_from_text(text: str) -> MetadataCountSpec:
    for spec in METADATA_COUNT_SPECS:
        if any(term.lower() in text.lower() for term in spec.route_terms):
            return spec
    return COUNT_SPECS_BY_CLI["posts"]


def _list_spec_from_text(text: str) -> MetadataCountSpec | None:
    for spec in METADATA_LIST_SPECS:
        if any(term.lower() in text.lower() for term in spec.route_terms):
            return spec
    return None


def route_task(intent_text: str) -> dict[str, object]:
    text = intent_text.strip()
    chat = _extract_chat(text)
    message_id_match = MESSAGE_ID_RE.search(text)
    if message_id_match and chat:
        message_id = int(message_id_match.group("message_id"))
        return {
            "ok": True,
            "command": "route",
            "intent": "get_message_by_id",
            "data_source": "live_telegram",
            "safety": "read-only",
            "confidence": 0.86,
            "chat": chat,
            "tool": "telegram_get_message",
            "execute": ["tg", "message", chat, str(message_id), "--json"],
            "needs_user_input": False,
            "next_action": "run_execute_command",
        }
    if COUNT_RE.search(text) or COUNT_POSTS_RE.search(text):
        spec = _count_spec_from_text(text)
        execute = ["tg", "count", spec.cli_name]
        if chat:
            execute.append(chat)
        execute.append("--json")
        return {
            "ok": True,
            "command": "route",
            "intent": f"count_channel_{spec.key}",
            "data_source": "live_telegram",
            "safety": "read-only",
            "confidence": 0.92 if chat else 0.72,
            "chat": chat,
            "tool": spec.tool_name,
            "execute": execute,
            "needs_user_input": chat is None,
            "next_action": "run_execute_command" if chat else "ask_for_chat",
            "notes": ["Uses Telegram history metadata; does not download the channel history."],
        }
    if LIST_RE.search(text):
        spec = _list_spec_from_text(text)
        if spec and spec.list_cli_name and spec.list_tool_name:
            execute = ["tg", "list", spec.list_cli_name]
            if chat:
                execute.append(chat)
            execute.extend(["--limit", "20", "--json"])
            return {
                "ok": True,
                "command": "route",
                "intent": f"list_channel_{spec.key}",
                "data_source": "live_telegram",
                "safety": "read-only",
                "confidence": 0.88 if chat else 0.68,
                "chat": chat,
                "tool": spec.list_tool_name,
                "execute": execute,
                "needs_user_input": chat is None,
                "next_action": "run_execute_command" if chat else "ask_for_chat",
                "notes": ["Uses Telegram server-side filter and bounded limit; does not export full history."],
            }
    if LATEST_RE.search(text):
        return {
            "ok": True,
            "command": "route",
            "intent": "latest_message_metadata",
            "data_source": "live_telegram",
            "safety": "read-only",
            "confidence": 0.82 if chat else 0.62,
            "chat": chat,
            "tool": "telegram_latest_message",
            "execute": ["tg", "latest", chat or "<chat>", "--json"],
            "needs_user_input": chat is None,
            "next_action": "run_execute_command" if chat else "ask_for_chat",
        }
    if INFO_RE.search(text):
        return {
            "ok": True,
            "command": "route",
            "intent": "dialog_metadata",
            "data_source": "live_telegram",
            "safety": "read-only",
            "confidence": 0.78 if chat else 0.58,
            "chat": chat,
            "tool": "telegram_dialog_metadata",
            "execute": ["tg", "info", chat or "<chat>", "--json"],
            "needs_user_input": chat is None,
            "next_action": "run_execute_command" if chat else "ask_for_chat",
        }
    if SEARCH_RE.search(text):
        return {
            "ok": True,
            "command": "route",
            "intent": "live_search",
            "data_source": "live_telegram",
            "safety": "read-only",
            "confidence": 0.7,
            "chat": chat,
            "tool": "telegram_search",
            "execute": ["tg", "search", chat or "<chat>", "<query>", "--json"],
            "needs_user_input": chat is None,
            "next_action": "run_execute_command" if chat else "ask_for_chat_and_query",
        }
    if TODAY_RE.search(text):
        return {
            "ok": True,
            "command": "route",
            "intent": "live_today",
            "data_source": "live_telegram",
            "safety": "read-only",
            "confidence": 0.7,
            "chat": chat,
            "tool": "telegram_read",
            "execute": ["tg", "read", "today", chat or "<chat>", "--limit", "30", "--json"],
            "needs_user_input": chat is None,
            "next_action": "run_execute_command" if chat else "ask_for_chat",
        }
    return {
        "ok": True,
        "command": "route",
        "intent": "unknown",
        "data_source": None,
        "safety": "plan-only",
        "confidence": 0.0,
        "chat": chat,
        "tool": None,
        "execute": [],
        "needs_user_input": True,
        "next_action": "use_tg_help_or_mcp_resource",
    }


async def cmd_doctor(*, timeout: float, endpoint: str | None, env_file: str | None, account: str) -> dict[str, object]:
    payload, elapsed, attempt = await call_tool_with_failover(
        tool_name="doctor_check",
        arguments={},
        timeout=timeout,
        explicit_endpoint=endpoint,
        env_file=env_file,
        account=account,
    )
    return _wrap_ok(
        command="doctor",
        endpoint=attempt.endpoint,
        endpoint_port=attempt.port or None,
        elapsed_seconds=elapsed,
        payload=payload,
        intent="health",
    )


async def cmd_read_today(
    *,
    chat: str,
    day: str,
    limit: int,
    timeout: float,
    endpoint: str | None,
    env_file: str | None,
    account: str,
) -> dict[str, object]:
    payload, elapsed, attempt = await call_tool_with_failover(
        tool_name="telegram_read",
        arguments={"chat": chat, "day": day, "limit": limit, "mode": "fast"},
        timeout=timeout,
        explicit_endpoint=endpoint,
        env_file=env_file,
        account=account,
    )
    duration_ms = round(elapsed * 1000, 3)
    from .agent_preflight import observe_fast_read

    observe_fast_read(tool="tg_read_today", status="ok", source="tg_cli", duration_ms=duration_ms)
    record_telemetry(
        "tg_read_today",
        status="ok",
        duration_ms=duration_ms,
        source="tg_cli",
        endpoint_port=attempt.port or None,
        arg_chat=chat,
        arg_day=day,
        arg_limit=limit,
        **telemetry_fields_from_result(payload if isinstance(payload, dict) else None),
    )
    return _wrap_ok(
        command="read today",
        endpoint=attempt.endpoint,
        endpoint_port=attempt.port or None,
        elapsed_seconds=elapsed,
        payload=payload,
        intent="live_today",
    )


async def cmd_read_recent(
    *,
    chat: str,
    limit: int,
    timeout: float,
    endpoint: str | None,
    env_file: str | None,
    account: str,
) -> dict[str, object]:
    payload, elapsed, attempt = await call_tool_with_failover(
        tool_name="telegram_read",
        arguments={"chat": chat, "limit": limit, "mode": "fast"},
        timeout=timeout,
        explicit_endpoint=endpoint,
        env_file=env_file,
        account=account,
    )
    record_telemetry(
        "tg_read_recent",
        status="ok",
        duration_ms=round(elapsed * 1000, 3),
        source="tg_cli",
        endpoint_port=attempt.port or None,
        arg_chat=chat,
        arg_limit=limit,
        **telemetry_fields_from_result(payload if isinstance(payload, dict) else None),
    )
    return _wrap_ok(
        command="read recent",
        endpoint=attempt.endpoint,
        endpoint_port=attempt.port or None,
        elapsed_seconds=elapsed,
        payload=payload,
        intent="live_recent",
    )


async def cmd_search(
    *,
    chat: str,
    query: str,
    limit: int,
    timeout: float,
    endpoint: str | None,
    env_file: str | None,
    account: str,
) -> dict[str, object]:
    payload, elapsed, attempt = await call_tool_with_failover(
        tool_name="telegram_search",
        arguments={"chat": chat, "query": query, "limit": limit},
        timeout=timeout,
        explicit_endpoint=endpoint,
        env_file=env_file,
        account=account,
    )
    record_telemetry(
        "tg_search",
        status="ok",
        duration_ms=round(elapsed * 1000, 3),
        source="tg_cli",
        endpoint_port=attempt.port or None,
        arg_chat=chat,
        **telemetry_fields_from_result(payload if isinstance(payload, dict) else None),
    )
    return _wrap_ok(
        command="search",
        endpoint=attempt.endpoint,
        endpoint_port=attempt.port or None,
        elapsed_seconds=elapsed,
        payload=payload,
        intent="live_search",
    )


async def cmd_count_metadata(
    *,
    chat: str,
    spec: MetadataCountSpec,
    timeout: float,
    endpoint: str | None,
    env_file: str | None,
    account: str,
) -> dict[str, object]:
    payload, elapsed, attempt = await call_tool_with_failover(
        tool_name=spec.tool_name,
        arguments={"chat": chat},
        timeout=timeout,
        explicit_endpoint=endpoint,
        env_file=env_file,
        account=account,
    )
    record_telemetry(
        f"tg_count_{spec.key}",
        status="ok",
        duration_ms=round(elapsed * 1000, 3),
        source="tg_cli",
        endpoint_port=attempt.port or None,
        arg_chat=chat,
        **telemetry_fields_from_result(payload if isinstance(payload, dict) else None),
    )
    return _wrap_ok(
        command=f"count {spec.cli_name}",
        endpoint=attempt.endpoint,
        endpoint_port=attempt.port or None,
        elapsed_seconds=elapsed,
        payload=payload,
        intent=f"count_channel_{spec.key}",
    )


async def cmd_count_posts(
    *,
    chat: str,
    timeout: float,
    endpoint: str | None,
    env_file: str | None,
    account: str,
) -> dict[str, object]:
    return await cmd_count_metadata(
        chat=chat,
        spec=COUNT_SPECS_BY_CLI["posts"],
        timeout=timeout,
        endpoint=endpoint,
        env_file=env_file,
        account=account,
    )


async def cmd_list_metadata(
    *,
    chat: str,
    spec: MetadataCountSpec,
    limit: int,
    offset_id: int,
    timeout: float,
    endpoint: str | None,
    env_file: str | None,
    account: str,
) -> dict[str, object]:
    if not spec.list_tool_name:
        raise McpCliError(f"{spec.cli_name} does not support bounded list")
    payload, elapsed, attempt = await call_tool_with_failover(
        tool_name=spec.list_tool_name,
        arguments={"chat": chat, "limit": limit, "offset_id": offset_id},
        timeout=timeout,
        explicit_endpoint=endpoint,
        env_file=env_file,
        account=account,
    )
    record_telemetry(
        f"tg_list_{spec.key}",
        status="ok",
        duration_ms=round(elapsed * 1000, 3),
        source="tg_cli",
        endpoint_port=attempt.port or None,
        arg_chat=chat,
        arg_limit=limit,
        arg_offset_id=offset_id,
        **telemetry_fields_from_result(payload if isinstance(payload, dict) else None),
    )
    return _wrap_ok(
        command=f"list {spec.list_cli_name}",
        endpoint=attempt.endpoint,
        endpoint_port=attempt.port or None,
        elapsed_seconds=elapsed,
        payload=payload,
        intent=f"list_channel_{spec.key}",
    )


async def cmd_latest(
    *,
    chat: str,
    timeout: float,
    endpoint: str | None,
    env_file: str | None,
    account: str,
) -> dict[str, object]:
    payload, elapsed, attempt = await call_tool_with_failover(
        tool_name="telegram_latest_message",
        arguments={"chat": chat},
        timeout=timeout,
        explicit_endpoint=endpoint,
        env_file=env_file,
        account=account,
    )
    record_telemetry(
        "tg_latest_message",
        status="ok",
        duration_ms=round(elapsed * 1000, 3),
        source="tg_cli",
        endpoint_port=attempt.port or None,
        arg_chat=chat,
        **telemetry_fields_from_result(payload if isinstance(payload, dict) else None),
    )
    return _wrap_ok(
        command="latest",
        endpoint=attempt.endpoint,
        endpoint_port=attempt.port or None,
        elapsed_seconds=elapsed,
        payload=payload,
        intent="latest_message_metadata",
    )


async def cmd_info(
    *,
    chat: str,
    timeout: float,
    endpoint: str | None,
    env_file: str | None,
    account: str,
) -> dict[str, object]:
    payload, elapsed, attempt = await call_tool_with_failover(
        tool_name="telegram_dialog_metadata",
        arguments={"chat": chat},
        timeout=timeout,
        explicit_endpoint=endpoint,
        env_file=env_file,
        account=account,
    )
    record_telemetry(
        "tg_dialog_metadata",
        status="ok",
        duration_ms=round(elapsed * 1000, 3),
        source="tg_cli",
        endpoint_port=attempt.port or None,
        arg_chat=chat,
        **telemetry_fields_from_result(payload if isinstance(payload, dict) else None),
    )
    return _wrap_ok(
        command="info",
        endpoint=attempt.endpoint,
        endpoint_port=attempt.port or None,
        elapsed_seconds=elapsed,
        payload=payload,
        intent="dialog_metadata",
    )


async def cmd_message(
    *,
    chat: str,
    message_id: int,
    timeout: float,
    endpoint: str | None,
    env_file: str | None,
    account: str,
) -> dict[str, object]:
    payload, elapsed, attempt = await call_tool_with_failover(
        tool_name="telegram_get_message",
        arguments={"chat": chat, "message_id": message_id},
        timeout=timeout,
        explicit_endpoint=endpoint,
        env_file=env_file,
        account=account,
    )
    record_telemetry(
        "tg_get_message",
        status="ok",
        duration_ms=round(elapsed * 1000, 3),
        source="tg_cli",
        endpoint_port=attempt.port or None,
        arg_chat=chat,
        arg_message_id=message_id,
        **telemetry_fields_from_result(payload if isinstance(payload, dict) else None),
    )
    return _wrap_ok(
        command="message",
        endpoint=attempt.endpoint,
        endpoint_port=attempt.port or None,
        elapsed_seconds=elapsed,
        payload=payload,
        intent="get_message_by_id",
    )


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", help="Emit JSON envelope.")
    common.add_argument("--timeout", type=float, default=20.0)
    common.add_argument("--env-file", default="~/.telegram-mcp/launchd.env")
    common.add_argument("--endpoint", default=None)
    common.add_argument("--account", choices=tuple(ACCOUNT_ENDPOINTS), default="main")

    parser = argparse.ArgumentParser(
        prog="tg",
        description="Fast live Telegram reads via local MCP (skill-first, no @telegram).",
    )
    parser.add_argument("--json", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--timeout", type=float, default=20.0, help=argparse.SUPPRESS)
    parser.add_argument("--env-file", default="~/.telegram-mcp/launchd.env", help=argparse.SUPPRESS)
    parser.add_argument("--endpoint", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--account", choices=tuple(ACCOUNT_ENDPOINTS), default="main", help=argparse.SUPPRESS)

    sub = parser.add_subparsers(dest="command", required=True)

    route = sub.add_parser("route", parents=[common], help="Plan the Telegram action without executing it")
    route.add_argument("intent", nargs="+")
    route.set_defaults(handler="route")

    doctor = sub.add_parser("doctor", parents=[common], help="Light MCP health via doctor_check")
    doctor.set_defaults(handler="doctor")

    read = sub.add_parser("read", parents=[common], help="Live read (today or recent)")
    read_sub = read.add_subparsers(dest="read_mode", required=True)

    today = read_sub.add_parser("today", parents=[common], help="Messages for one calendar day (live only)")
    today.add_argument("chat")
    today.add_argument("--day", default=date.today().isoformat())
    today.add_argument("--limit", type=int, default=30)
    today.set_defaults(handler="read_today")

    recent = read_sub.add_parser("recent", parents=[common], help="Recent live messages (not archive)")
    recent.add_argument("chat")
    recent.add_argument("--limit", type=int, default=30)
    recent.set_defaults(handler="read_recent")

    search = sub.add_parser("search", parents=[common], help="Search within one live dialog")
    search.add_argument("chat")
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=20)
    search.set_defaults(handler="search")

    count = sub.add_parser("count", parents=[common], help="Read-only Telegram counts")
    count_sub = count.add_subparsers(dest="count_mode", required=True)

    for spec in METADATA_COUNT_SPECS:
        count_parser = count_sub.add_parser(spec.cli_name, parents=[common], help=f"Total visible {spec.label}")
        count_parser.add_argument("chat")
        count_parser.set_defaults(handler="count_metadata", count_kind=spec.cli_name)

    list_parser = sub.add_parser("list", parents=[common], help="Bounded read-only Telegram filtered message slices")
    list_sub = list_parser.add_subparsers(dest="list_mode", required=True)

    for spec in METADATA_LIST_SPECS:
        list_mode = list_sub.add_parser(spec.list_cli_name, parents=[common], help=f"Recent visible {spec.label}")
        list_mode.add_argument("chat")
        list_mode.add_argument("--limit", type=int, default=20)
        list_mode.add_argument("--offset-id", type=int, default=0)
        list_mode.set_defaults(handler="list_metadata", list_kind=spec.list_cli_name)

    latest = sub.add_parser("latest", parents=[common], help="Latest visible message metadata")
    latest.add_argument("chat")
    latest.set_defaults(handler="latest")

    info = sub.add_parser("info", parents=[common], help="Resolved dialog metadata")
    info.add_argument("chat")
    info.set_defaults(handler="info")

    message = sub.add_parser("message", parents=[common], help="Get one message by id")
    message.add_argument("chat")
    message.add_argument("message_id", type=int)
    message.set_defaults(handler="message")

    return parser


async def run_command(args: argparse.Namespace) -> dict[str, object]:
    env_file = args.env_file
    endpoint = args.endpoint
    timeout = args.timeout
    account = args.account

    if args.handler == "route":
        return route_task(" ".join(args.intent))
    if args.handler == "doctor":
        return await cmd_doctor(timeout=timeout, endpoint=endpoint, env_file=env_file, account=account)
    if args.handler == "read_today":
        return await cmd_read_today(
            chat=args.chat,
            day=args.day,
            limit=args.limit,
            timeout=timeout,
            endpoint=endpoint,
            env_file=env_file,
            account=account,
        )
    if args.handler == "read_recent":
        return await cmd_read_recent(
            chat=args.chat,
            limit=args.limit,
            timeout=timeout,
            endpoint=endpoint,
            env_file=env_file,
            account=account,
        )
    if args.handler == "search":
        return await cmd_search(
            chat=args.chat,
            query=args.query,
            limit=args.limit,
            timeout=timeout,
            endpoint=endpoint,
            env_file=env_file,
            account=account,
        )
    if args.handler == "count_metadata":
        return await cmd_count_metadata(
            chat=args.chat,
            spec=COUNT_SPECS_BY_CLI[args.count_kind],
            timeout=timeout,
            endpoint=endpoint,
            env_file=env_file,
            account=account,
        )
    if args.handler == "list_metadata":
        return await cmd_list_metadata(
            chat=args.chat,
            spec=LIST_SPECS_BY_CLI[args.list_kind],
            limit=args.limit,
            offset_id=args.offset_id,
            timeout=timeout,
            endpoint=endpoint,
            env_file=env_file,
            account=account,
        )
    if args.handler == "latest":
        return await cmd_latest(
            chat=args.chat,
            timeout=timeout,
            endpoint=endpoint,
            env_file=env_file,
            account=account,
        )
    if args.handler == "info":
        return await cmd_info(
            chat=args.chat,
            timeout=timeout,
            endpoint=endpoint,
            env_file=env_file,
            account=account,
        )
    if args.handler == "message":
        return await cmd_message(
            chat=args.chat,
            message_id=args.message_id,
            timeout=timeout,
            endpoint=endpoint,
            env_file=env_file,
            account=account,
        )
    raise McpCliError(f"unknown handler: {args.handler}")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        output = asyncio.run(run_command(args))
    except Exception as exc:
        output = _wrap_err(command=getattr(args, "handler", "unknown"), exc=exc)

    if args.json or not sys.stdout.isatty():
        print(json.dumps(output, ensure_ascii=False, indent=2))
    elif output.get("ok"):
        print(f"ok: {output.get('command')} in {output.get('elapsed_seconds')}s")
        payload = output.get("payload")
        if isinstance(payload, dict) and "messages" in payload:
            print(f"messages: {len(payload.get('messages') or [])}")
    else:
        print(f"error: {output.get('error')}", file=sys.stderr)

    return 0 if output.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
