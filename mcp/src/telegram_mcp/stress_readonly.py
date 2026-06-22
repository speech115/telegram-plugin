"""Read-only daemon stress harness for telegram-mcp."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from dataclasses import dataclass
from typing import Any

from .mcp_http_client import call_tool_with_failover


READONLY_CALLS = {
    "telegram.get_me",
    "telegram.resolve_dialog",
    "telegram.collect_dialog_context",
    "telegram.read_today_dialog",
    "telegram.search_dialog_messages",
}


@dataclass(frozen=True)
class _CallSpec:
    tool: str
    args: tuple[str, ...]


@dataclass(frozen=True)
class _CallResult:
    result: dict[str, Any]
    pair_id: int | None = None
    pair_position: str | None = None


def _positive_int(raw_value: str) -> int:
    value = int(raw_value)
    if value < 1:
        raise argparse.ArgumentTypeError("must be >= 1")
    return value


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a bounded read-only stress check against telegram-mcp daemon."
    )
    parser.add_argument("--iterations", type=_positive_int, default=12)
    parser.add_argument("--concurrency", type=_positive_int, default=4)
    parser.add_argument("--timeout", type=_positive_int, default=30000)
    parser.add_argument(
        "--mode",
        choices=("readonly", "cache-pair"),
        default="readonly",
        help=(
            "readonly runs the normal read-only rotation; cache-pair repeats identical "
            "facade calls in sequential pairs for cache-hit latency diagnostics"
        ),
    )
    parser.add_argument(
        "--chat",
        help="Optional dialog id/ref for facade read calls. Defaults to Saved Messages via resolve_dialog.",
    )
    parser.add_argument(
        "--search-query",
        default=".",
        help="Query for telegram.search_dialog_messages stress calls.",
    )
    parser.add_argument("--endpoint", default=None)
    parser.add_argument("--env-file", default="~/.telegram-mcp/launchd.env")
    parser.add_argument("--account", choices=("main", "pl"), default="main")
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


def _parse_tool_args(args: tuple[str, ...]) -> dict[str, object]:
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


async def _run_mcp_call(
    spec: _CallSpec,
    *,
    endpoint: str | None,
    env_file: str | None,
    account: str,
) -> dict[str, Any]:
    if spec.tool not in READONLY_CALLS:
        raise ValueError(f"Unsafe stress tool: {spec.tool}")

    started_at = time.perf_counter()
    process_timeout = _process_timeout_seconds(spec.args)
    try:
        payload, _elapsed, _attempt = await call_tool_with_failover(
            tool_name=spec.tool.removeprefix("telegram."),
            arguments=_parse_tool_args(spec.args),
            timeout=process_timeout or 30.0,
            explicit_endpoint=endpoint,
            env_file=env_file,
            account=account,
        )
        stdout_text = json.dumps(payload, ensure_ascii=False)
        stderr_text = ""
        exit_code = 0
        ok = True
    except Exception as exc:
        stdout_text = ""
        stderr_text = f"{type(exc).__name__}: {exc}"
        exit_code = -1
        ok = False
    duration_ms = (time.perf_counter() - started_at) * 1000
    return {
        "tool": spec.tool,
        "ok": ok,
        "exit_code": exit_code,
        "duration_ms": round(duration_ms, 3),
        "stdout_bytes": len(stdout_text.encode("utf-8")),
        "stderr": stderr_text[-1000:] if stderr_text else "",
        "stdout": stdout_text,
    }


def _process_timeout_seconds(args: tuple[str, ...]) -> float | None:
    try:
        index = args.index("--timeout")
        timeout_ms = int(args[index + 1])
    except (ValueError, IndexError):
        return None
    return max(1.0, timeout_ms / 1000) + 5.0


async def _discover_chat(
    *,
    timeout: int,
    endpoint: str | None,
    env_file: str | None,
    account: str,
) -> tuple[str | None, str | None]:
    result = await _run_mcp_call(
        _CallSpec(
            "telegram.resolve_dialog",
            ("query=me", "--timeout", str(timeout), "--output", "json"),
        ),
        endpoint=endpoint,
        env_file=env_file,
        account=account,
    )
    if not result["ok"]:
        return None, "telegram.resolve_dialog discovery failed"
    try:
        payload = json.loads(result["stdout"] or "{}")
    except json.JSONDecodeError:
        return None, "telegram.resolve_dialog discovery returned non-JSON"
    if payload.get("isError"):
        return None, "telegram.resolve_dialog discovery returned tool error"
    dialog_id = payload.get("dialog_ref") or payload.get("id")
    if dialog_id is None:
        return None, "telegram.resolve_dialog discovery returned no dialog_ref"
    return str(dialog_id), None


def _build_call_plan(
    *,
    iterations: int,
    timeout: int,
    chat: str | None,
    search_query: str,
) -> list[_CallSpec]:
    base_plan = [
        _CallSpec("telegram.get_me", ("--timeout", str(timeout), "--output", "json")),
        _CallSpec(
            "telegram.resolve_dialog",
            ("query=me", "--timeout", str(timeout), "--output", "json"),
        ),
    ]
    if chat:
        base_plan.append(
            _CallSpec(
                "telegram.collect_dialog_context",
                (
                    f"chat={chat}",
                    "mode=fast",
                    "recent_limit=1",
                    "include_pinned=false",
                    "include_voice_transcription=false",
                    "--timeout",
                    str(timeout),
                    "--output",
                    "json",
                ),
            )
        )
        base_plan.append(
            _CallSpec(
                "telegram.read_today_dialog",
                (
                    f"chat={chat}",
                    "limit=1",
                    "include_voice_transcription=false",
                    "include_sender_name=false",
                    "--timeout",
                    str(timeout),
                    "--output",
                    "json",
                ),
            )
        )
        base_plan.append(
            _CallSpec(
                "telegram.search_dialog_messages",
                (
                    f"chat={chat}",
                    f"query={search_query}",
                    "limit=1",
                    "include_sender_name=false",
                    "--timeout",
                    str(timeout),
                    "--output",
                    "json",
                ),
            )
        )
    return [base_plan[index % len(base_plan)] for index in range(iterations)]


def _build_cache_pair_plan(
    *,
    iterations: int,
    timeout: int,
    chat: str | None,
    search_query: str,
) -> tuple[list[_CallSpec], list[str]]:
    warnings: list[str] = []
    if not chat:
        warnings.append("cache-pair facade calls skipped because no chat was resolved")
        return [], warnings

    pair_templates = [
        _CallSpec(
            "telegram.collect_dialog_context",
            (
                f"chat={chat}",
                "mode=fast",
                "recent_limit=1",
                "include_pinned=false",
                "include_voice_transcription=false",
                "--timeout",
                str(timeout),
                "--output",
                "json",
            ),
        ),
        _CallSpec(
            "telegram.read_today_dialog",
            (
                f"chat={chat}",
                "limit=1",
                "include_voice_transcription=false",
                "include_sender_name=false",
                "--timeout",
                str(timeout),
                "--output",
                "json",
            ),
        ),
        _CallSpec(
            "telegram.search_dialog_messages",
            (
                f"chat={chat}",
                f"query={search_query}",
                "limit=1",
                "include_sender_name=false",
                "--timeout",
                str(timeout),
                "--output",
                "json",
            ),
        ),
    ]

    call_plan: list[_CallSpec] = []
    while len(call_plan) < iterations:
        template = pair_templates[(len(call_plan) // 2) % len(pair_templates)]
        call_plan.extend((template, template))
    return call_plan[:iterations], warnings


async def _run_plan(
    call_plan: list[_CallSpec],
    concurrency: int,
    endpoint: str | None,
    env_file: str | None,
    account: str,
) -> list[dict[str, Any]]:
    semaphore = asyncio.Semaphore(concurrency)

    async def run_one(spec: _CallSpec) -> dict[str, Any]:
        async with semaphore:
            return await _run_mcp_call(
                spec,
                endpoint=endpoint,
                env_file=env_file,
                account=account,
            )

    return await asyncio.gather(*(run_one(spec) for spec in call_plan))


async def _run_cache_pair_plan(
    call_plan: list[_CallSpec],
    endpoint: str | None,
    env_file: str | None,
    account: str,
) -> list[_CallResult]:
    results: list[_CallResult] = []
    for index, spec in enumerate(call_plan):
        result = await _run_mcp_call(
            spec,
            endpoint=endpoint,
            env_file=env_file,
            account=account,
        )
        results.append(
            _CallResult(
                result=result,
                pair_id=index // 2,
                pair_position="first" if index % 2 == 0 else "second",
            )
        )
    return results


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = round((percentile / 100) * (len(ordered) - 1))
    index = max(0, min(len(ordered) - 1, index))
    return round(ordered[index], 3)


def _summarize(
    results: list[_CallResult],
    *,
    warnings: list[str],
    chat: str | None,
    concurrency: int,
    mode: str,
) -> dict[str, Any]:
    by_tool: dict[str, dict[str, Any]] = {}
    cache_pairs_by_id: dict[int, dict[str, Any]] = {}
    for wrapped in results:
        result = wrapped.result
        tool = result["tool"]
        tool_summary = by_tool.setdefault(
            tool,
            {
                "calls": 0,
                "succeeded": 0,
                "failed": 0,
                "durations_ms": [],
            },
        )
        tool_summary["calls"] += 1
        if result["ok"]:
            tool_summary["succeeded"] += 1
        else:
            tool_summary["failed"] += 1
        tool_summary["durations_ms"].append(result["duration_ms"])
        if wrapped.pair_id is not None and wrapped.pair_position is not None:
            pair = cache_pairs_by_id.setdefault(
                wrapped.pair_id,
                {"pair_id": wrapped.pair_id, "tool": tool},
            )
            pair[wrapped.pair_position] = {
                "ok": result["ok"],
                "duration_ms": result["duration_ms"],
                "exit_code": result["exit_code"],
            }

    for tool_summary in by_tool.values():
        durations = tool_summary.pop("durations_ms")
        tool_summary["avg_duration_ms"] = (
            round(sum(durations) / len(durations), 3) if durations else 0.0
        )
        tool_summary["p95_duration_ms"] = _percentile(durations, 95)
        tool_summary["max_duration_ms"] = round(max(durations), 3) if durations else 0.0

    cache_pairs = [
        cache_pairs_by_id[pair_id] for pair_id in sorted(cache_pairs_by_id.keys())
    ]
    for pair in cache_pairs:
        first = pair.get("first")
        second = pair.get("second")
        if first and second:
            pair["delta_ms"] = round(second["duration_ms"] - first["duration_ms"], 3)
            if first["duration_ms"] > 0:
                pair["second_to_first_ratio"] = round(
                    second["duration_ms"] / first["duration_ms"], 3
                )

    total = len(results)
    succeeded = sum(1 for wrapped in results if wrapped.result["ok"])
    failures = [
        {
            "tool": wrapped.result["tool"],
            "exit_code": wrapped.result["exit_code"],
            "stderr": wrapped.result["stderr"],
        }
        for wrapped in results
        if not wrapped.result["ok"]
    ]
    return {
        "status": "ok" if succeeded == total else "error",
        "mode": mode,
        "total_calls": total,
        "succeeded": succeeded,
        "failed": total - succeeded,
        "concurrency": concurrency,
        "chat": chat,
        "tools": by_tool,
        "cache_pairs": cache_pairs,
        "warnings": warnings,
        "failures": failures,
    }


def _print_text_summary(summary: dict[str, Any]) -> None:
    print("telegram-mcp read-only stress")
    print(f"status: {summary['status']}")
    print(
        f"calls: {summary['succeeded']}/{summary['total_calls']} succeeded "
        f"(concurrency={summary['concurrency']})"
    )
    for tool, item in summary["tools"].items():
        print(
            f"{tool}: {item['succeeded']}/{item['calls']} ok, "
            f"avg={item['avg_duration_ms']}ms, p95={item['p95_duration_ms']}ms, "
            f"max={item['max_duration_ms']}ms"
        )
    for warning in summary["warnings"]:
        print(f"warning: {warning}")
    for failure in summary["failures"][:5]:
        print(
            f"failure: {failure['tool']} exit={failure['exit_code']} "
            f"{failure['stderr']}"
        )


async def _main_async(args: argparse.Namespace) -> int:
    warnings: list[str] = []
    chat = args.chat
    if chat is None:
        chat, warning = await _discover_chat(
            timeout=args.timeout,
            endpoint=args.endpoint,
            env_file=args.env_file,
            account=args.account,
        )
        if warning:
            warnings.append(warning)

    if args.mode == "cache-pair":
        call_plan, pair_warnings = _build_cache_pair_plan(
            iterations=args.iterations,
            timeout=args.timeout,
            chat=chat,
            search_query=args.search_query,
        )
        warnings.extend(pair_warnings)
        results = await _run_cache_pair_plan(
            call_plan=call_plan,
            endpoint=args.endpoint,
            env_file=args.env_file,
            account=args.account,
        )
    else:
        call_plan = _build_call_plan(
            iterations=args.iterations,
            timeout=args.timeout,
            chat=chat,
            search_query=args.search_query,
        )
        plain_results = await _run_plan(
            call_plan=call_plan,
            concurrency=args.concurrency,
            endpoint=args.endpoint,
            env_file=args.env_file,
            account=args.account,
        )
        results = [_CallResult(result=result) for result in plain_results]
    summary = _summarize(
        results,
        warnings=warnings,
        chat=chat,
        concurrency=args.concurrency,
        mode=args.mode,
    )
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        _print_text_summary(summary)
    return 0 if summary["status"] == "ok" else 1


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return asyncio.run(_main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
