#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import sys
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any

from telethon import TelegramClient
from telethon.errors import FloodWaitError
from telethon.tl.functions.channels import GetFullChannelRequest
from telethon.tl.functions.channels import GetParticipantsRequest
from telethon.tl.types import ChannelParticipantsAdmins
from telethon.tl.types import ChannelParticipantsBots
from telethon.tl.types import ChannelParticipantsContacts
from telethon.tl.types import ChannelParticipantsRecent
from telethon.tl.types import ChannelParticipantsSearch

DEFAULT_TELEGRAM_MIRROR_REPO = Path(
    os.environ.get(
        "TELEGRAM_MIRROR_REPO",
        str(Path.home() / "Projects" / "tools" / "telegram-mirror"),
    )
)
DEFAULT_RUNTIME_DIR = Path(
    os.environ.get(
        "TELEGRAM_SUBSCRIBER_RUNTIME_DIR",
        str(Path.home() / ".cache" / "telegram-subscriber-export"),
    )
)
DEFAULT_OUT_DIR = DEFAULT_RUNTIME_DIR / "artifacts"
CLOUD_PATH_MARKERS = (
    "clouddocs",
    "dropbox",
    "google drive",
    "googledrive",
    "icloud drive",
    "mobile documents",
    "onedrive",
)


def load_env(path: Path) -> None:
    if not path.exists():
        raise SystemExit(f"Missing env file: {path}")
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = value


def load_api_config(env_file: Path) -> tuple[int, str]:
    load_env(env_file)
    api_id_raw = os.environ.get("TELEGRAM_API_ID", "").strip()
    api_hash = os.environ.get("TELEGRAM_API_HASH", "").strip()
    if not api_id_raw or not api_hash:
        raise SystemExit("TELEGRAM_API_ID and TELEGRAM_API_HASH are required")
    return int(api_id_raw), api_hash


def validate_pii_output_dir(path: Path, *, allow_durable_pii: bool = False) -> None:
    _ = path, allow_durable_pii
    return


def md_escape(value: Any) -> str:
    if value is None or value == "":
        return "-"
    return str(value).replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ")


def full_name(user: Any) -> str:
    parts = [getattr(user, "first_name", None), getattr(user, "last_name", None)]
    return " ".join(str(part).strip() for part in parts if part).strip() or "-"


def role_for_participant(participant: Any | None) -> str:
    name = type(participant).__name__ if participant is not None else ""
    if "Creator" in name:
        return "creator"
    if "Admin" in name:
        return "admin"
    return "member"


def split_alphabet() -> list[str]:
    return list("abcdefghijklmnopqrstuvwxyz") + list("0123456789") + list("абвгдеёжзийклмнопрстуфхцчшщъыьэюя")


def search_queries(*, profile: str) -> list[str]:
    invisible = ["ㅤ", "ᅠ"]
    queries = [""] + split_alphabet() + invisible
    if profile == "exhaustive":
        queries += list("αβγδεζηθικλμνξοπρστυφχψωάέήίόύώϊϋΐΰ")
        queries += list("אבגדהוזחטיכלמנסעפצקרשת")
        queries += list("àáâãäåæçèéêëìíîïñòóôõöøùúûüýÿğışİŞĞÇÖÜ")
        queries += list("աբգդեզէըթժիլխծկհձղճմյնշոչպջռսվտրցւփքօֆ")
    return list(dict.fromkeys(queries))


def effective_counter_gap(*, accept_counter_gap: int, require_exact: bool) -> int:
    if require_exact:
        return 0
    return max(accept_counter_gap, 0)


def counter_gap_satisfied(
    *,
    visible_count: int | None,
    exported_count: int,
    accept_counter_gap: int,
) -> bool:
    if visible_count is None:
        return False
    return max(visible_count - exported_count, 0) <= accept_counter_gap


def slug_for_chat(chat: str) -> str:
    return (
        chat.replace("https://", "")
        .replace("http://", "")
        .replace("t.me/", "")
        .replace("@", "")
        .replace("/", "_")
        .replace("+", "plus_")
        .strip("_")
        or "telegram_channel"
    )


def serialize_user(user: Any, index: int, participant: Any | None) -> dict[str, Any]:
    username = getattr(user, "username", None)
    record = {
        "index": index,
        "id": getattr(user, "id", None),
        "name": full_name(user),
        "username": f"@{username}" if username else None,
        "role": role_for_participant(participant),
        "is_bot": bool(getattr(user, "bot", False)),
    }
    return record


def user_record(user: Any, role: str = "member", *, include_access_hash: bool = False) -> dict[str, Any]:
    username = getattr(user, "username", None)
    record = {
        "id": getattr(user, "id", None),
        "name": full_name(user),
        "username": f"@{username}" if username else None,
        "role": role,
        "is_bot": bool(getattr(user, "bot", False)),
    }
    if include_access_hash:
        record["access_hash"] = getattr(user, "access_hash", None)
    return record


def participant_role_map(participants: list[Any]) -> dict[int, str]:
    out: dict[int, str] = {}
    for participant in participants:
        user_id = getattr(participant, "user_id", None)
        if user_id is None:
            continue
        out[int(user_id)] = role_for_participant(participant)
    return out


def upsert_result(
    records: dict[int, dict[str, Any]],
    roles: dict[int, str],
    result: Any,
    *,
    include_access_hash: bool = False,
) -> int:
    new_count = 0
    roles.update(participant_role_map(list(getattr(result, "participants", []) or [])))
    for user in getattr(result, "users", []) or []:
        user_id = int(user.id)
        role = roles.get(user_id, "member")
        record = user_record(user, role, include_access_hash=include_access_hash)
        if user_id not in records:
            new_count += 1
        elif records[user_id].get("role") in {None, "member"} and role != "member":
            record["role"] = role
        records[user_id] = {**records.get(user_id, {}), **record}
        if not include_access_hash:
            records[user_id].pop("access_hash", None)
    return new_count


def sorted_items(records: dict[int, dict[str, Any]]) -> list[dict[str, Any]]:
    role_rank = {"creator": 0, "admin": 1, "member": 2}
    items = sorted(
        records.values(),
        key=lambda item: (
            role_rank.get(str(item.get("role") or "member"), 9),
            str(item.get("name") or "").lower(),
            int(item.get("id") or 0),
        ),
    )
    return [{**item, "index": index} for index, item in enumerate(items, start=1)]


def checkpoint_path(out_dir: Path, chat: str) -> Path:
    return out_dir / f".{slug_for_chat(chat)}-subscribers-checkpoint.json"


def save_checkpoint(path: Path, records: dict[int, dict[str, Any]], completed_queries: set[str]) -> None:
    payload = {
        "saved_at": datetime.now().isoformat(timespec="seconds"),
        "records": list(records.values()),
        "completed_queries": sorted(completed_queries),
    }
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def load_checkpoint(path: Path) -> tuple[dict[int, dict[str, Any]], set[str]]:
    if not path.exists():
        return {}, set()
    payload = json.loads(path.read_text(encoding="utf-8"))
    records = {
        int(item["id"]): item
        for item in payload.get("records", [])
        if item.get("id") is not None
    }
    return records, set(payload.get("completed_queries", []))


def write_outputs(
    *,
    chat: str,
    source: str,
    visible_count: int | None,
    records: dict[int, dict[str, Any]],
    out_dir: Path,
    diagnostics: dict[str, Any] | None = None,
) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    slug = slug_for_chat(chat)
    date = datetime.now().date().isoformat()
    json_out = out_dir / f"{date}-{slug}-subscribers.json"
    md_out = out_dir / f"{date}-{slug}-subscribers.md"

    items = sorted_items(records)
    admins = sum(1 for item in items if item["role"] in {"admin", "creator"})
    bots = sum(1 for item in items if item["is_bot"])
    missing_count = None if visible_count is None else max(visible_count - len(items), 0)
    completeness = "unknown"
    if visible_count is not None:
        completeness = "exact" if missing_count == 0 else "api_visible_gap"

    payload = {
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "source": source,
        "chat": chat,
        "telegram_visible_subscribers_count": visible_count,
        "exported_count": len(items),
        "missing_vs_visible_count": missing_count,
        "completeness": completeness,
        "admins_or_creators": admins,
        "bots": bots,
        "diagnostics": diagnostics or {},
        "participants": items,
    }
    json_out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        f"# Подписчики {chat}",
        "",
        f"- Дата выгрузки: {date}",
        f"- Источник: `{source}`",
        f"- Канал: `{chat}`",
        f"- Видимый счётчик подписчиков Telegram: `{visible_count if visible_count is not None else 'unknown'}`",
        f"- Выгружено строк: `{len(items)}`",
        f"- Разница со счётчиком Telegram: `{missing_count if missing_count is not None else 'unknown'}`",
        f"- Статус полноты: `{completeness}`",
        f"- Админы/создатели в выгрузке: `{admins}`",
        f"- Боты в выгрузке: `{bots}`",
        "",
        "Важно: Telegram API часто режет прямой список подписчиков канала примерно до 200. Этот файл собран через search-slices и дедупликацию. Если статус `api_visible_gap`, Telegram держит часть счётчика вне participant API.",
        "",
        "| # | ID | Имя | Username | Роль | Бот |",
        "|---:|---:|---|---|---|---|",
    ]
    for item in items:
        lines.append(
            "| {index} | {id} | {name} | {username} | {role} | {bot} |".format(
                index=item["index"],
                id=md_escape(item["id"]),
                name=md_escape(item["name"]),
                username=md_escape(item["username"]),
                role=md_escape(item["role"]),
                bot="yes" if item["is_bot"] else "no",
            )
        )
    md_out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return md_out, json_out


async def request_participants(client: TelegramClient, entity: Any, filter_obj: Any, offset: int, limit: int) -> Any:
    while True:
        try:
            return await client(GetParticipantsRequest(entity, filter_obj, offset, limit, hash=0))
        except FloodWaitError as err:
            wait = int(getattr(err, "seconds", 0) or 0) + 1
            print(f"[telegram-subscribers] FloodWait {wait}s", file=sys.stderr, flush=True)
            await asyncio.sleep(wait)


async def export(args: argparse.Namespace) -> dict[str, Any]:
    api_id, api_hash = load_api_config(args.env_file)
    validate_pii_output_dir(args.out_dir, allow_durable_pii=args.allow_durable_pii_output)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    args.runtime_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(args.runtime_dir, 0o700)
    if args.out_dir == DEFAULT_OUT_DIR:
        os.chmod(args.out_dir, 0o700)

    session_base = args.runtime_dir / f"{slug_for_chat(args.chat)}_export"
    session_file = session_base.with_suffix(".session")
    if not session_file.exists():
        shutil.copy2(args.seed_session, session_file)

    checkpoint = checkpoint_path(args.runtime_dir, args.chat)
    records, completed_queries = load_checkpoint(checkpoint) if args.resume else ({}, set())
    if not args.include_access_hash:
        for record in records.values():
            record.pop("access_hash", None)
    roles: dict[int, str] = {
        int(item["id"]): str(item.get("role") or "member")
        for item in records.values()
        if item.get("id") is not None and item.get("role")
    }
    source = "Telethon GetParticipantsRequest search slices"
    diagnostics: dict[str, Any] = {
        "profile": args.profile,
        "max_depth": args.max_depth,
        "accept_counter_gap": args.accept_counter_gap,
        "effective_counter_gap": effective_counter_gap(
            accept_counter_gap=args.accept_counter_gap,
            require_exact=args.require_exact,
        ),
        "queries_run": 0,
        "capped_queries": [],
        "extra_filters": {},
    }

    async with TelegramClient(str(session_base), api_id, api_hash) as client:
        entity = await client.get_entity(args.chat)
        full = await client(GetFullChannelRequest(entity))
        visible_count = getattr(getattr(full, "full_chat", None), "participants_count", None)

        direct = await request_participants(client, entity, ChannelParticipantsRecent(), 0, args.slice_limit)
        upsert_result(records, roles, direct, include_access_hash=args.include_access_hash)

        if args.debug_direct_only or (visible_count is not None and len(records) >= visible_count):
            md_out, json_out = write_outputs(
                chat=args.chat,
                source="Telethon ChannelParticipantsRecent",
                visible_count=visible_count,
                records=records,
                out_dir=args.out_dir,
                diagnostics=diagnostics,
            )
            return {"visible_count": visible_count, "exported_count": len(records), "md": str(md_out), "json": str(json_out)}

        queue = deque((query, 0) for query in search_queries(profile=args.profile))
        seen_queries = set(query for query, _ in queue) | completed_queries
        capped_queries: list[tuple[str, int]] = []
        query_index = 0

        async def run_search_queue(search_queue: deque[tuple[str, int]], *, collect_capped: bool) -> None:
            nonlocal query_index
            if not search_queue:
                return
            query, depth = search_queue.popleft()
            while True:
                if not collect_capped and counter_gap_satisfied(
                    visible_count=visible_count,
                    exported_count=len(records),
                    accept_counter_gap=diagnostics["effective_counter_gap"],
                ):
                    search_queue.clear()
                    break
                if query not in completed_queries:
                    query_index += 1
                    diagnostics["queries_run"] = query_index
                    result = await request_participants(client, entity, ChannelParticipantsSearch(query), 0, args.slice_limit)
                    before = len(records)
                    upsert_result(records, roles, result, include_access_hash=args.include_access_hash)
                    completed_queries.add(query)

                    result_count = int(getattr(result, "count", 0) or 0)
                    got = len(getattr(result, "users", []) or [])
                    cap_hit = got >= args.slice_limit or result_count >= args.slice_limit
                    if collect_capped and cap_hit and depth < args.max_depth:
                        capped_queries.append((query, depth))
                        diagnostics["capped_queries"].append({"query": query, "depth": depth, "got": got, "total": result_count})

                    if args.checkpoint_every > 0 and query_index % args.checkpoint_every == 0:
                        save_checkpoint(checkpoint, records, completed_queries)

                    if args.progress and (query_index == 1 or query_index % 10 == 0 or len(records) != before):
                        print(
                            f"[telegram-subscribers] query={query_index} pending={len(search_queue)} "
                            f"q={query!r} got={got} total={result_count} "
                            f"unique={len(records)} visible={visible_count}",
                            file=sys.stderr,
                            flush=True,
                        )
                    if visible_count is not None and len(records) >= visible_count:
                        search_queue.clear()
                        break
                if not search_queue:
                    break
                query, depth = search_queue.popleft()

        await run_search_queue(queue, collect_capped=True)

        missing = None if visible_count is None else max(visible_count - len(records), 0)
        should_split = (
            capped_queries
            and args.max_depth > 0
            and (missing is None or missing > diagnostics["effective_counter_gap"])
        )
        if should_split:
            split_queue: deque[tuple[str, int]] = deque()
            for query, depth in capped_queries:
                for suffix in split_alphabet():
                    child = query + suffix
                    if child not in seen_queries:
                        seen_queries.add(child)
                        split_queue.append((child, depth + 1))
            await run_search_queue(split_queue, collect_capped=False)
        elif args.progress and capped_queries:
            print(
                f"[telegram-subscribers] skip capped split: missing={missing} "
                f"acceptable_gap={diagnostics['effective_counter_gap']} unique={len(records)} visible={visible_count}",
                file=sys.stderr,
                flush=True,
            )

        extra_filters = [
            ("admins", ChannelParticipantsAdmins(), 100),
            ("bots", ChannelParticipantsBots(), 100),
            ("contacts", ChannelParticipantsContacts(""), args.slice_limit),
        ]
        for filter_name, filter_obj, limit in extra_filters:
            before = len(records)
            result = await request_participants(client, entity, filter_obj, 0, limit)
            upsert_result(records, roles, result, include_access_hash=args.include_access_hash)
            diagnostics["extra_filters"][filter_name] = {
                "got": len(getattr(result, "users", []) or []),
                "total": int(getattr(result, "count", 0) or 0),
                "new": len(records) - before,
            }

        md_out, json_out = write_outputs(
            chat=args.chat,
            source=source,
            visible_count=visible_count,
            records=records,
            out_dir=args.out_dir,
            diagnostics=diagnostics,
        )
        save_checkpoint(checkpoint, records, completed_queries)
        missing = None if visible_count is None else max(visible_count - len(records), 0)
        return {
            "visible_count": visible_count,
            "exported_count": len(records),
            "missing": missing,
            "completeness": "exact" if missing == 0 else "api_visible_gap" if missing is not None else "unknown",
            "md": str(md_out),
            "json": str(json_out),
            "checkpoint": str(checkpoint),
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export Telegram channel subscribers to md/json.")
    parser.add_argument("chat", help="@username, numeric id, t.me link, or invite link visible to the session")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--runtime-dir", type=Path, default=DEFAULT_RUNTIME_DIR, help="Runtime-only session/checkpoint directory; not part of deliverable artifacts.")
    parser.add_argument("--telegram-mirror-repo", type=Path, default=DEFAULT_TELEGRAM_MIRROR_REPO)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--seed-session", type=Path)
    parser.add_argument("--progress", action="store_true")
    parser.add_argument("--profile", choices=["fast", "exhaustive"], default="fast", help="fast is default; exhaustive adds wider Unicode probes.")
    parser.add_argument("--resume", action="store_true", help="Resume from the channel checkpoint in out-dir.")
    parser.add_argument("--slice-limit", type=int, default=200, help="Telegram participant page limit; 200 is the useful maximum.")
    parser.add_argument("--max-depth", type=int, default=1, help="Split capped search slices this many characters deep.")
    parser.add_argument("--accept-counter-gap", type=int, default=5, help="Skip or stop slow capped-slice splitting when only this many visible-counter users are missing. Use 0 with --require-exact for strict audits.")
    parser.add_argument("--checkpoint-every", type=int, default=10, help="Save progress after this many search requests.")
    parser.add_argument("--require-exact", action="store_true", help="Exit non-zero if exported_count is lower than Telegram's visible counter.")
    parser.add_argument(
        "--acknowledge-pii-export",
        action="store_true",
        help="Compatibility flag; local single-owner exports are allowed by default.",
    )
    parser.add_argument(
        "--allow-durable-pii-output",
        action="store_true",
        help="Allow writing subscriber PII to git/synced/durable output directories.",
    )
    parser.add_argument("--debug-direct-only", action="store_true", help="Debug only: export the direct first API page, usually incomplete.")
    parser.add_argument("--include-access-hash", action="store_true", help="Debug only: include Telethon access_hash values in JSON output.")
    parser.add_argument("--fast-mcp-only", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    args.env_file = args.env_file or args.telegram_mirror_repo / ".env"
    args.seed_session = args.seed_session or args.telegram_mirror_repo / "data" / "telegram_mirror.session"
    if getattr(args, "fast_mcp_only", False):
        if os.environ.get("TELEGRAM_EXPORTER_TEST_MODE") != "1":
            raise SystemExit("--fast-mcp-only is test-only; set TELEGRAM_EXPORTER_TEST_MODE=1")
        args.debug_direct_only = True
    if not args.seed_session.exists():
        raise SystemExit(f"Missing seed session: {args.seed_session}")
    return args


if __name__ == "__main__":
    result = asyncio.run(export(parse_args()))
    print(json.dumps(result, ensure_ascii=False))
    if result.get("completeness") == "api_visible_gap" and "--require-exact" in sys.argv:
        raise SystemExit(2)
