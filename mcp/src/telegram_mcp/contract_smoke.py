"""External MCP contract smoke check for the telegram-mcp daemon."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Any


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


class ContractSmokeError(RuntimeError):
    """Raised when the external MCP contract smoke check fails."""


def _positive_int(raw_value: str) -> int:
    value = int(raw_value)
    if value < 1:
        raise argparse.ArgumentTypeError("must be >= 1")
    return value


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a safe external MCP contract smoke check through mcporter."
    )
    parser.add_argument("--timeout", type=_positive_int, default=30000)
    parser.add_argument("--search-query", default=SAFE_SEARCH_QUERY)
    parser.add_argument(
        "--profile",
        choices=("core", "app-media", "all"),
        default="core",
    )
    parser.add_argument("--check-cache-stats", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def _run_mcporter(
    mcporter_bin: str,
    args: list[str],
    *,
    label: str,
    timeout_ms: int,
) -> _CallResult:
    started_at = time.perf_counter()
    timeout_seconds = max(1.0, timeout_ms / 1000) + 5.0
    try:
        result = subprocess.run(
            [mcporter_bin, *args],
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
        exit_code = result.returncode
        stdout = result.stdout.strip()
        stderr = result.stderr.strip()
    except subprocess.TimeoutExpired as error:
        exit_code = -1
        stdout = (error.stdout or "").strip() if isinstance(error.stdout, str) else ""
        stderr = f"mcporter process timed out after {timeout_seconds:g}s"

    return _CallResult(
        label=label,
        ok=exit_code == 0,
        exit_code=exit_code,
        duration_ms=round((time.perf_counter() - started_at) * 1000, 3),
        stdout=stdout,
        stderr=stderr[-1000:] if stderr else "",
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
        raise ContractSmokeError(f"mcporter list telegram missing tools: {missing}")
    return sorted(required_tools)


def _extract_text_tool_names(output: str) -> set[str]:
    return set(re.findall(r"\bfunction\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", output))


def _load_tool_catalog(
    mcporter_bin: str,
    *,
    timeout: int,
    profile: str,
    results: list[_CallResult],
) -> list[str]:
    json_result = _run_mcporter(
        mcporter_bin,
        ["list", "telegram", "--json"],
        label="mcporter list telegram --json",
        timeout_ms=timeout,
    )
    results.append(json_result)
    try:
        return _require_tools(_load_json(json_result), profile=profile)
    except ContractSmokeError:
        text_result = _run_mcporter(
            mcporter_bin,
            ["list", "telegram"],
            label="mcporter list telegram",
            timeout_ms=timeout,
        )
        results.append(text_result)
        if not text_result.ok:
            raise ContractSmokeError(
                "mcporter list telegram failed as JSON and text output"
            )
        names = _extract_text_tool_names(text_result.stdout)
        if not names:
            raise ContractSmokeError("mcporter list telegram returned no parseable tools")
        return _require_tool_names(names, profile=profile)


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
    mcporter_bin: str,
    *,
    timeout: int,
    results: list[_CallResult],
) -> dict[str, Any]:
    payload = _call_json(
        mcporter_bin,
        "telegram.doctor_check",
        [],
        timeout=timeout,
        results=results,
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
    mcporter_bin: str,
    tool: str,
    args: list[str],
    *,
    timeout: int,
    results: list[_CallResult],
) -> Any:
    result = _run_mcporter(
        mcporter_bin,
        ["call", tool, *args, "--timeout", str(timeout), "--output", "json"],
        label=tool,
        timeout_ms=timeout,
    )
    results.append(result)
    return _load_json(result)


def run_contract_smoke(
    *,
    mcporter_bin: str,
    timeout: int,
    search_query: str,
    profile: str = "core",
    check_cache_stats: bool = False,
) -> dict[str, Any]:
    results: list[_CallResult] = []

    listed_tools = _load_tool_catalog(
        mcporter_bin,
        timeout=timeout,
        profile=profile,
        results=results,
    )

    dialog_payload = _call_json(
        mcporter_bin,
        "telegram.resolve_dialog",
        ["query=me"],
        timeout=timeout,
        results=results,
    )
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
    cache_stats_before = (
        _doctor_runtime_stats(mcporter_bin, timeout=timeout, results=results)
        if check_cache_stats
        else None
    )

    if profile in {"core", "all"}:
        _require_collect_shape(
            _call_json(
                mcporter_bin,
                "telegram.collect_dialog_context",
                collect_args,
                timeout=timeout,
                results=results,
            )
        )
        _require_collect_shape(
            _call_json(
                mcporter_bin,
                "telegram.collect_dialog_context",
                collect_args,
                timeout=timeout,
                results=results,
            )
        )

        _require_prepare_shape(
            _call_json(
                mcporter_bin,
                "telegram.prepare_dialog_reply",
                prepare_args,
                timeout=timeout,
                results=results,
            )
        )

        _require_search_shape(
            _call_json(
                mcporter_bin,
                "telegram.search_dialog_messages",
                search_args,
                timeout=timeout,
                results=results,
            )
        )
        if check_cache_stats:
            _require_search_shape(
                _call_json(
                    mcporter_bin,
                    "telegram.search_dialog_messages",
                    search_args,
                    timeout=timeout,
                    results=results,
                )
            )

    if profile in {"app-media", "all"}:
        _require_dialog_handle_shape(
            _call_json(
                mcporter_bin,
                "telegram.find_dialog",
                [f"query={dialog_ref}"],
                timeout=timeout,
                results=results,
            ),
            "telegram.find_dialog",
        )
        _require_message_shape(
            _require_dict(
                _call_json(
                    mcporter_bin,
                    "telegram.read_dialog",
                    [
                        f"chat={dialog_ref}",
                        "limit=1",
                        "include_voice_transcription=false",
                        "include_sender_name=false",
                    ],
                    timeout=timeout,
                    results=results,
                ),
                "telegram.read_dialog",
            ),
            "telegram.read_dialog",
        )
        _require_collect_shape(
            _call_json(
                mcporter_bin,
                "telegram.collect_context",
                collect_args,
                timeout=timeout,
                results=results,
            )
        )
        if check_cache_stats:
            _require_collect_shape(
                _call_json(
                    mcporter_bin,
                    "telegram.collect_context",
                    collect_args,
                    timeout=timeout,
                    results=results,
                )
            )
        _require_prepare_shape(
            _call_json(
                mcporter_bin,
                "telegram.draft_reply",
                prepare_args,
                timeout=timeout,
                results=results,
            )
        )
        _require_send_preview_shape(
            _call_json(
                mcporter_bin,
                "telegram.prepare_send_message",
                [f"chat={dialog_ref}", "text=contract smoke preview only"],
                timeout=timeout,
                results=results,
            ),
            "telegram.prepare_send_message",
        )
        _require_send_preview_shape(
            _call_json(
                mcporter_bin,
                "telegram.prepare_reply_message",
                [
                    f"chat={dialog_ref}",
                    "message_id=1",
                    "text=contract smoke reply preview only",
                ],
                timeout=timeout,
                results=results,
            ),
            "telegram.prepare_reply_message",
        )
        _require_media_manifest_shape(
            _call_json(
                mcporter_bin,
                "telegram.prepare_media_inspection_manifest",
                [f"chat={dialog_ref}", "limit=3"],
                timeout=timeout,
                results=results,
            )
        )

    cache_stats_after = (
        _doctor_runtime_stats(mcporter_bin, timeout=timeout, results=results)
        if check_cache_stats
        else None
    )
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

    return {
        "status": "ok",
        "mode": "external_mcp_contract_smoke",
        "profile": profile,
        "mcporter": mcporter_bin,
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
    mcporter_bin = os.environ.get("MCPORTER_BIN") or shutil.which("mcporter")
    if not mcporter_bin:
        payload = {
            "status": "error",
            "error": "mcporter not found. Set MCPORTER_BIN or add mcporter to PATH.",
        }
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(payload["error"], file=sys.stderr)
        return 1

    try:
        summary = run_contract_smoke(
            mcporter_bin=mcporter_bin,
            timeout=args.timeout,
            search_query=args.search_query,
            profile=args.profile,
            check_cache_stats=args.check_cache_stats,
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
