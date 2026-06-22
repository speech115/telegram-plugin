"""External MCP contract smoke check for the telegram-mcp daemon."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from dataclasses import dataclass
from typing import Any

from .mcp_http_client import call_tool_with_failover, list_tools_with_failover


CORE_REQUIRED_TOOLS = {
    "collect_dialog_context",
    "prepare_dialog_reply",
    "resolve_dialog",
    "search_dialog_messages",
}
APP_MEDIA_REQUIRED_TOOLS = {
    "collect_context",
    "draft_reply",
    "find_dialog",
    "prepare_reply_message",
    "prepare_send_message",
    "prepare_media_inspection_manifest",
    "read_dialog",
}

SAFE_SEARCH_QUERY = "a"


@dataclass(frozen=True)
class _CallResult:
    label: str
    ok: bool
    exit_code: int
    duration_ms: float
    stdout: str
    stderr: str
    endpoint: str | None = None
    endpoint_port: int | None = None


class ContractSmokeError(RuntimeError):
    """Raised when the external MCP contract smoke check fails."""


def _positive_int(raw_value: str) -> int:
    value = int(raw_value)
    if value < 1:
        raise argparse.ArgumentTypeError("must be >= 1")
    return value


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a safe external MCP contract smoke check through the local MCP HTTP daemon."
    )
    parser.add_argument("--timeout", type=_positive_int, default=30000)
    parser.add_argument("--search-query", default=SAFE_SEARCH_QUERY)
    parser.add_argument(
        "--profile",
        choices=("core", "app-media", "all"),
        default="core",
    )
    parser.add_argument("--check-cache-stats", action="store_true")
    parser.add_argument("--endpoint", default=None)
    parser.add_argument("--env-file", default="~/.telegram-mcp/launchd.env")
    parser.add_argument(
        "--account",
        choices=("main", "pl", "recklessou", "teamsyncsage", "vermassov"),
        default="main",
    )
    parser.add_argument("--json", action="store_true")
    return parser


def _coerce_arg_value(value: str) -> object:
    if value == "true":
        return True
    if value == "false":
        return False
    try:
        return int(value)
    except ValueError:
        return value


def _parse_tool_args(args: list[str]) -> dict[str, object]:
    parsed: dict[str, object] = {}
    index = 0
    while index < len(args):
        item = args[index]
        if item in {"--timeout", "--output"}:
            index += 2
            continue
        if "=" in item:
            key, value = item.split("=", 1)
            parsed[key] = _coerce_arg_value(value)
        index += 1
    return parsed


def _run_mcp_tool(
    tool: str,
    args: list[str],
    *,
    label: str,
    timeout_ms: int,
    endpoint: str | None,
    env_file: str | None,
    account: str,
) -> _CallResult:
    started_at = time.perf_counter()
    timeout_seconds = max(1.0, timeout_ms / 1000)
    try:
        payload, _elapsed, attempt = asyncio.run(
            call_tool_with_failover(
                tool_name=tool.removeprefix("telegram."),
                arguments=_parse_tool_args(args),
                timeout=timeout_seconds,
                explicit_endpoint=endpoint,
                env_file=env_file,
                account=account,
            )
        )
        exit_code = 0
        stdout = json.dumps(payload, ensure_ascii=False)
        stderr = ""
        attempt_endpoint = getattr(attempt, "endpoint", None)
        attempt_port = getattr(attempt, "port", None)
    except Exception as error:
        exit_code = -1
        stdout = ""
        stderr = f"{type(error).__name__}: {error}"
        attempt_endpoint = None
        attempt_port = None

    return _CallResult(
        label=label,
        ok=exit_code == 0,
        exit_code=exit_code,
        duration_ms=round((time.perf_counter() - started_at) * 1000, 3),
        stdout=stdout,
        stderr=stderr[-1000:] if stderr else "",
        endpoint=attempt_endpoint,
        endpoint_port=attempt_port,
    )


def _load_json(result: _CallResult) -> Any:
    if not result.ok:
        raise ContractSmokeError(
            f"{result.label} failed with exit code {result.exit_code}: {result.stderr}"
        )
    try:
        return json.loads(result.stdout or "{}")
    except json.JSONDecodeError as error:
        raise ContractSmokeError(f"{result.label} returned non-JSON output") from error


def _extract_tool_names(payload: Any) -> set[str]:
    names: set[str] = set()

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            raw_name = value.get("name")
            if isinstance(raw_name, str):
                names.add(raw_name)
                if raw_name.startswith("telegram."):
                    names.add(raw_name.removeprefix("telegram."))
            for nested in value.values():
                visit(nested)
        elif isinstance(value, list):
            for item in value:
                visit(item)
        elif isinstance(value, str):
            names.add(value)
            if value.startswith("telegram."):
                names.add(value.removeprefix("telegram."))

    visit(payload)
    return names


def _required_tools_for_profile(profile: str) -> set[str]:
    if profile == "core":
        return set(CORE_REQUIRED_TOOLS)
    if profile == "app-media":
        return set(APP_MEDIA_REQUIRED_TOOLS)
    return set(CORE_REQUIRED_TOOLS | APP_MEDIA_REQUIRED_TOOLS)


def _require_tools(payload: Any, *, profile: str = "core") -> list[str]:
    names = _extract_tool_names(payload)
    return _require_tool_names(names, profile=profile)


def _require_tool_names(names: set[str], *, profile: str = "core") -> list[str]:
    required_tools = _required_tools_for_profile(profile)
    missing = sorted(required_tools - names)
    if missing:
        raise ContractSmokeError(f"MCP list_tools missing tools: {missing}")
    return sorted(required_tools)


def _load_tool_catalog(
    *,
    timeout: int,
    profile: str,
    results: list[_CallResult],
    endpoint: str | None,
    env_file: str | None,
    account: str,
) -> list[str]:
    started_at = time.perf_counter()
    try:
        names, _elapsed, attempt = asyncio.run(
            list_tools_with_failover(
                timeout=max(1.0, timeout / 1000),
                explicit_endpoint=endpoint,
                env_file=env_file,
                account=account,
            )
        )
        json_result = _CallResult(
            label="mcp list_tools",
            ok=True,
            exit_code=0,
            duration_ms=round((time.perf_counter() - started_at) * 1000, 3),
            stdout=json.dumps({"tools": [{"name": name} for name in names]}),
            stderr="",
            endpoint=getattr(attempt, "endpoint", None),
            endpoint_port=getattr(attempt, "port", None),
        )
    except Exception as error:
        json_result = _CallResult(
            label="mcp list_tools",
            ok=False,
            exit_code=-1,
            duration_ms=round((time.perf_counter() - started_at) * 1000, 3),
            stdout="",
            stderr=f"{type(error).__name__}: {error}",
        )
    results.append(json_result)
    return _require_tools(_load_json(json_result), profile=profile)


def _require_dict(payload: Any, label: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ContractSmokeError(f"{label} returned {type(payload).__name__}, expected object")
    return payload


def _dialog_ref_from_resolve(payload: Any) -> str:
    data = _require_dict(payload, "telegram.resolve_dialog")
    dialog_ref = data.get("dialog_ref") or data.get("id")
    if dialog_ref is None:
        raise ContractSmokeError("telegram.resolve_dialog has no dialog_ref or id")
    return str(dialog_ref)


def _require_chat(payload: dict[str, Any], label: str) -> None:
    chat = payload.get("chat")
    if not isinstance(chat, dict):
        raise ContractSmokeError(f"{label} missing chat object")
    if chat.get("id") is None and chat.get("dialog_ref") is None:
        raise ContractSmokeError(f"{label} chat has no id or dialog_ref")


def _require_message_shape(payload: dict[str, Any], label: str) -> None:
    _require_chat(payload, label)
    if not isinstance(payload.get("messages"), list):
        raise ContractSmokeError(f"{label} missing messages list")
    if not isinstance(payload.get("message_count"), int):
        raise ContractSmokeError(f"{label} missing integer message_count")


def _require_collect_shape(payload: Any) -> None:
    data = _require_dict(payload, "telegram.collect_dialog_context")
    _require_message_shape(data, "telegram.collect_dialog_context")
    if data.get("collection_mode") != "fast":
        raise ContractSmokeError("telegram.collect_dialog_context did not return fast mode")


def _require_prepare_shape(payload: Any) -> None:
    data = _require_dict(payload, "telegram.prepare_dialog_reply")
    _require_chat(data, "telegram.prepare_dialog_reply")
    if data.get("preview_only") is not True:
        raise ContractSmokeError("telegram.prepare_dialog_reply is not preview-only")
    if not isinstance(data.get("context"), dict):
        raise ContractSmokeError("telegram.prepare_dialog_reply missing context object")
    if not isinstance(data.get("send_tool"), str):
        raise ContractSmokeError("telegram.prepare_dialog_reply missing send_tool")
    if not isinstance(data.get("send_args_preview"), dict):
        raise ContractSmokeError("telegram.prepare_dialog_reply missing send_args_preview")


def _require_send_preview_shape(payload: Any, label: str) -> None:
    data = _require_dict(payload, label)
    _require_chat(data, label)
    if data.get("preview_only") is not True:
        raise ContractSmokeError(f"{label} is not preview-only")
    if not isinstance(data.get("send_tool"), str):
        raise ContractSmokeError(f"{label} missing send_tool")
    if not isinstance(data.get("send_args_preview"), dict):
        raise ContractSmokeError(f"{label} missing send_args_preview")


def _require_search_shape(payload: Any) -> None:
    data = _require_dict(payload, "telegram.search_dialog_messages")
    _require_message_shape(data, "telegram.search_dialog_messages")


def _require_dialog_handle_shape(payload: Any, label: str) -> None:
    data = _require_dict(payload, label)
    if data.get("id") is None and data.get("dialog_ref") is None:
        raise ContractSmokeError(f"{label} missing id or dialog_ref")
    if not isinstance(data.get("resolved_from"), str):
        raise ContractSmokeError(f"{label} missing resolved_from")


def _require_media_manifest_shape(payload: Any) -> None:
    data = _require_dict(payload, "telegram.prepare_media_inspection_manifest")
    _require_chat(data, "telegram.prepare_media_inspection_manifest")
    if not isinstance(data.get("items"), list):
        raise ContractSmokeError("telegram.prepare_media_inspection_manifest missing items list")
    if not isinstance(data.get("media_count"), int):
        raise ContractSmokeError("telegram.prepare_media_inspection_manifest missing media_count")
    if data.get("download_tool") != "download_dialog_media":
        raise ContractSmokeError("telegram.prepare_media_inspection_manifest missing download_tool")


def _doctor_runtime_stats(
    *,
    timeout: int,
    results: list[_CallResult],
    endpoint: str | None,
    env_file: str | None,
    account: str,
) -> dict[str, Any]:
    payload = _call_json(
        "telegram.doctor_check",
        [],
        timeout=timeout,
        results=results,
        endpoint=endpoint,
        env_file=env_file,
        account=account,
    )
    data = _require_dict(payload, "telegram.doctor_check")
    stats = data.get("runtime_stats")
    if not isinstance(stats, dict):
        raise ContractSmokeError("telegram.doctor_check missing runtime_stats")
    return stats


def _stat_value(stats: dict[str, Any], key: str) -> int:
    value = stats.get(key, 0)
    return int(value) if isinstance(value, int | float) else 0


def _call_json(
    tool: str,
    args: list[str],
    *,
    timeout: int,
    results: list[_CallResult],
    endpoint: str | None,
    env_file: str | None,
    account: str,
) -> Any:
    result = _run_mcp_tool(
        tool,
        args,
        label=tool,
        timeout_ms=timeout,
        endpoint=endpoint,
        env_file=env_file,
        account=account,
    )
    results.append(result)
    return _load_json(result)


def run_contract_smoke(
    *,
    timeout: int,
    search_query: str,
    profile: str = "core",
    check_cache_stats: bool = False,
    endpoint: str | None = None,
    env_file: str | None = None,
    account: str = "main",
) -> dict[str, Any]:
    results: list[_CallResult] = []

    listed_tools = _load_tool_catalog(
        timeout=timeout,
        profile=profile,
        results=results,
        endpoint=endpoint,
        env_file=env_file,
        account=account,
    )

    def call(tool: str, args: list[str]) -> Any:
        return _call_json(
            tool,
            args,
            timeout=timeout,
            results=results,
            endpoint=endpoint,
            env_file=env_file,
            account=account,
        )

    def stats() -> dict[str, Any]:
        return _doctor_runtime_stats(
            timeout=timeout,
            results=results,
            endpoint=endpoint,
            env_file=env_file,
            account=account,
        )

    dialog_payload = call("telegram.resolve_dialog", ["query=me"])
    dialog_ref = _dialog_ref_from_resolve(dialog_payload)

    collect_args = [
        f"chat={dialog_ref}",
        "mode=fast",
        "recent_limit=1",
        "include_pinned=false",
        "include_voice_transcription=false",
    ]
    safe_query = search_query.strip() or SAFE_SEARCH_QUERY
    search_args = [
        f"chat={dialog_ref}",
        f"query={safe_query}",
        "limit=1",
        "include_sender_name=false",
    ]
    prepare_args = [
        f"chat={dialog_ref}",
        "goal=contract smoke preview only",
        "context_limit=1",
        "mode=fast",
    ]
    cache_stats_before = stats() if check_cache_stats else None

    if profile in {"core", "all"}:
        _require_collect_shape(
            call(
                "telegram.collect_dialog_context",
                collect_args,
            )
        )
        _require_collect_shape(
            call(
                "telegram.collect_dialog_context",
                collect_args,
            )
        )

        _require_prepare_shape(
            call(
                "telegram.prepare_dialog_reply",
                prepare_args,
            )
        )

        _require_search_shape(
            call(
                "telegram.search_dialog_messages",
                search_args,
            )
        )
        if check_cache_stats:
            _require_search_shape(
                call(
                    "telegram.search_dialog_messages",
                    search_args,
                )
            )

    if profile in {"app-media", "all"}:
        _require_dialog_handle_shape(
            call(
                "telegram.find_dialog",
                [f"query={dialog_ref}"],
            ),
            "telegram.find_dialog",
        )
        _require_message_shape(
            _require_dict(
                call(
                    "telegram.read_dialog",
                    [
                        f"chat={dialog_ref}",
                        "limit=1",
                        "include_voice_transcription=false",
                        "include_sender_name=false",
                    ],
                ),
                "telegram.read_dialog",
            ),
            "telegram.read_dialog",
        )
        _require_collect_shape(
            call(
                "telegram.collect_context",
                collect_args,
            )
        )
        if check_cache_stats:
            _require_collect_shape(
                call(
                    "telegram.collect_context",
                    collect_args,
                )
            )
        _require_prepare_shape(
            call(
                "telegram.draft_reply",
                prepare_args,
            )
        )
        _require_send_preview_shape(
            call(
                "telegram.prepare_send_message",
                [f"chat={dialog_ref}", "text=contract smoke preview only"],
            ),
            "telegram.prepare_send_message",
        )
        _require_send_preview_shape(
            call(
                "telegram.prepare_reply_message",
                [
                    f"chat={dialog_ref}",
                    "message_id=1",
                    "text=contract smoke reply preview only",
                ],
            ),
            "telegram.prepare_reply_message",
        )
        _require_media_manifest_shape(
            call(
                "telegram.prepare_media_inspection_manifest",
                [f"chat={dialog_ref}", "limit=3"],
            )
        )

    cache_stats_after = stats() if check_cache_stats else None
    cache_stats_delta: dict[str, int] | None = None
    if check_cache_stats and cache_stats_before is not None and cache_stats_after is not None:
        cache_stats_delta = {
            key: _stat_value(cache_stats_after, key) - _stat_value(cache_stats_before, key)
            for key in (
                "dialog_read_cache_hit",
                "dialog_search_cache_hit",
            )
        }
        if cache_stats_delta["dialog_read_cache_hit"] <= 0:
            raise ContractSmokeError("dialog_read_cache_hit did not increase")
        if profile in {"core", "all"} and cache_stats_delta["dialog_search_cache_hit"] <= 0:
            raise ContractSmokeError("dialog_search_cache_hit did not increase")

    endpoint_result = next((result for result in results if result.endpoint_port is not None), None)

    return {
        "status": "ok",
        "mode": "external_mcp_contract_smoke",
        "profile": profile,
        "transport": "mcp_http_client",
        "account": account,
        "endpoint": endpoint_result.endpoint if endpoint_result else None,
        "endpoint_port": endpoint_result.endpoint_port if endpoint_result else None,
        "dialog": dialog_ref,
        "listed_tools": listed_tools,
        "cache_stats_delta": cache_stats_delta,
        "calls": [
            {
                "label": result.label,
                "ok": result.ok,
                "exit_code": result.exit_code,
                "duration_ms": result.duration_ms,
                "stderr": result.stderr,
                "endpoint": result.endpoint,
                "endpoint_port": result.endpoint_port,
            }
            for result in results
        ],
    }


def _print_text_summary(summary: dict[str, Any]) -> None:
    print("telegram-mcp external contract smoke")
    print(f"status: {summary['status']}")
    print(f"profile: {summary['profile']}")
    print(f"dialog: {summary['dialog']}")
    print(f"tools: {', '.join(summary['listed_tools'])}")
    for item in summary["calls"]:
        print(f"{item['label']}: exit={item['exit_code']} {item['duration_ms']}ms")


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        summary = run_contract_smoke(
            timeout=args.timeout,
            search_query=args.search_query,
            profile=args.profile,
            check_cache_stats=args.check_cache_stats,
            endpoint=args.endpoint,
            env_file=args.env_file,
            account=args.account,
        )
    except ContractSmokeError as error:
        payload = {"status": "error", "error": str(error)}
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(str(error), file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        _print_text_summary(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
