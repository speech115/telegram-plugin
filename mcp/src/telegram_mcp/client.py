"""Telegram client wrapper with high-level methods."""

from __future__ import annotations

import asyncio
import json
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, TypeVar

import structlog
from telethon import TelegramClient

from .client_chats import ChatOperationsMixin
from .client_contacts import ContactOperationsMixin
from .client_groups import GroupOperationsMixin
from .client_media import MediaOperationsMixin
from .client_messages import MessageOperationsMixin
from .client_privacy import PrivacyOperationsMixin
from .client_profile import ProfileOperationsMixin
from .client_stories import StoryOperationsMixin
from .config import Settings
from .download_cleanup import cleanup_download_dir, estimate_download_cleanup
from .errors import ToolContractError
from .locking import FileSessionLock
from .scheduler import TelegramOperationScheduler
from .types import (
    DoctorInfo,
    HealthInfo,
)
from .utils import resolve_entity

log = structlog.get_logger()
T = TypeVar("T")


class TelegramWrapper(
    MessageOperationsMixin,
    ChatOperationsMixin,
    GroupOperationsMixin,
    MediaOperationsMixin,
    ContactOperationsMixin,
    StoryOperationsMixin,
    ProfileOperationsMixin,
    PrivacyOperationsMixin,
):
    """High-level wrapper around TelegramClient."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = TelegramClient(
            settings.build_session(),
            settings.api_id,
            settings.api_hash,
            connection_retries=10,
            retry_delay=2,
            auto_reconnect=True,
            request_retries=3,
        )
        self._session_lock: FileSessionLock | None = None
        self._entity_cache: OrderedDict[str | int, Any] = OrderedDict()
        self._input_entity_cache: OrderedDict[str | int, Any] = OrderedDict()
        self._dialog_ref_entity_cache: OrderedDict[str, Any] = OrderedDict()
        self._dialog_ref_input_entity_cache: OrderedDict[str, Any] = OrderedDict()
        self._result_cache: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self._cache_ttl: int = settings.cache_ttl
        self._dialog_read_cache_ttl: int = self._bounded_setting(
            settings,
            "dialog_read_cache_ttl_seconds",
            5,
        )
        self._result_cache_size: int = settings.result_cache_size
        self._read_inflight_calls: OrderedDict[
            tuple[Any, ...],
            asyncio.Task[Any],
        ] = OrderedDict()
        self._read_inflight_lock = asyncio.Lock()
        self._read_inflight_dedupe_size = self._bounded_setting(
            settings,
            "read_inflight_dedupe_size",
            128,
        )
        self._transcript_cache: OrderedDict[tuple[int, int], str] = OrderedDict()
        self._transcript_cache_size = self._bounded_setting(
            settings,
            "transcript_cache_size",
            256,
        )
        self._runtime_stats: dict[str, int | float] = {
            "dialog_read_cache_hit": 0,
            "dialog_read_cache_miss": 0,
            "dialog_search_cache_hit": 0,
            "dialog_search_cache_miss": 0,
            "cache_invalidated_after_write": 0,
            "download_media_batch_dedupe_count": 0,
            "download_media_batch_effective_concurrency": 0,
        }
        self._dialog_send_confirmations: dict[str, tuple[float, dict[str, object]]] = {}
        self._last_download_cleanup_at: float = 0.0
        self._connect_lock = asyncio.Lock()
        self._scheduler = TelegramOperationScheduler(
            read_concurrency=settings.scheduler_read_concurrency,
            write_concurrency=settings.scheduler_write_concurrency,
            media_concurrency=settings.scheduler_media_concurrency,
            transcribe_concurrency=settings.scheduler_transcribe_concurrency,
            enrich_concurrency=settings.scheduler_enrich_concurrency,
            circuit_breaker_enabled=settings.circuit_breaker_enabled,
            circuit_breaker_failure_threshold=settings.circuit_breaker_failure_threshold,
            circuit_breaker_recovery_seconds=settings.circuit_breaker_recovery_seconds,
        )

    @staticmethod
    def _bounded_setting(settings: Settings, name: str, default: int) -> int:
        value = getattr(settings, name, default)
        if not isinstance(value, int | str | float):
            value = default
        try:
            return max(0, int(value))
        except (TypeError, ValueError):
            return default

    def _emit_diagnostic(self, event: str, **fields: Any) -> None:
        if not self.settings.mcp_include_diagnostics:
            return
        log.info(event, **fields)

    def _increment_runtime_stat(self, name: str, value: int = 1) -> None:
        current = self._runtime_stats.get(name, 0)
        if isinstance(current, float):
            self._runtime_stats[name] = current + value
            return
        self._runtime_stats[name] = int(current) + value

    def _set_runtime_stat(self, name: str, value: int | float) -> None:
        self._runtime_stats[name] = value

    def _runtime_stats_snapshot(self) -> dict[str, object]:
        snapshot: dict[str, object] = dict(self._runtime_stats)

        def hit_rate(hit_key: str, miss_key: str) -> float | None:
            hits = int(self._runtime_stats.get(hit_key, 0))
            misses = int(self._runtime_stats.get(miss_key, 0))
            total = hits + misses
            if total <= 0:
                return None
            return round(hits / total, 4)

        snapshot["dialog_read_cache_hit_rate"] = hit_rate(
            "dialog_read_cache_hit",
            "dialog_read_cache_miss",
        )
        snapshot["dialog_search_cache_hit_rate"] = hit_rate(
            "dialog_search_cache_hit",
            "dialog_search_cache_miss",
        )
        return snapshot

    def _record_cache_access_stat(self, key: str, *, hit: bool) -> None:
        outcome = "hit" if hit else "miss"
        if key.startswith("dialog_read:"):
            self._increment_runtime_stat(f"dialog_read_cache_{outcome}")
        elif key.startswith("dialog_search:"):
            self._increment_runtime_stat(f"dialog_search_cache_{outcome}")

    def _maybe_cleanup_download_dir(self) -> None:
        retention_days = self.settings.download_retention_days
        if retention_days <= 0:
            return

        now = time.time()
        interval = self.settings.download_cleanup_interval_seconds
        if interval > 0 and now - self._last_download_cleanup_at < interval:
            return

        self._last_download_cleanup_at = now
        try:
            result = cleanup_download_dir(
                self.settings.download_dir,
                retention_days,
                now=now,
            )
        except Exception as exc:
            log.warning(
                "telegram_download_cleanup_failed",
                download_dir=str(self.settings.download_dir),
                retention_days=retention_days,
                error=f"{type(exc).__name__}: {exc}",
            )
            return
        if result.deleted_files or result.errors:
            log.info(
                "telegram_download_cleanup_completed",
                download_dir=str(self.settings.download_dir),
                retention_days=retention_days,
                deleted_files=result.deleted_files,
                deleted_bytes=result.deleted_bytes,
                errors=list(result.errors),
            )

    def _emit_cache_event(
        self,
        event: str,
        *,
        key: str,
        reason: str | None = None,
        item_count: int | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "key_prefix": key.split(":", 1)[0],
            "cache_size": len(self._result_cache),
        }
        if reason is not None:
            payload["reason"] = reason
        if item_count is not None:
            payload["item_count"] = item_count
        self._emit_diagnostic(event, **payload)

    def _emit_read_timing(
        self,
        operation: str,
        started_at: float,
        **fields: Any,
    ) -> None:
        duration_ms = round((time.perf_counter() - started_at) * 1000, 3)
        self._emit_diagnostic(
            "telegram_read_completed",
            operation=operation,
            duration_ms=duration_ms,
            **fields,
        )

    async def connect(self) -> None:
        self.settings.ensure_dirs()
        self._acquire_session_lock()
        try:
            async with self._connect_lock:
                await asyncio.wait_for(
                    self.client.connect(),
                    timeout=self.settings.connect_timeout_seconds,
                )
                if not await self.client.is_user_authorized():
                    raise RuntimeError(
                        "Not authorized. Run 'telegram-mcp login' first."
                    )
        except asyncio.TimeoutError as exc:
            self._release_session_lock()
            raise RuntimeError(
                "Telegram connection timed out after "
                f"{self.settings.connect_timeout_seconds:g}s"
            ) from exc
        except BaseException:
            self._release_session_lock()
            raise

    async def ensure_connected(self) -> None:
        """Reconnect if the Telegram connection was lost."""
        if self.client.is_connected():
            return
        async with self._connect_lock:
            if self.client.is_connected():
                return
            try:
                await asyncio.wait_for(
                    self.client.connect(),
                    timeout=self.settings.connect_timeout_seconds,
                )
            except asyncio.TimeoutError as exc:
                raise RuntimeError(
                    "Telegram reconnection timed out after "
                    f"{self.settings.connect_timeout_seconds:g}s"
                ) from exc
            if not await self.client.is_user_authorized():
                raise RuntimeError(
                    "Telegram session expired after reconnect. "
                    "Run 'telegram-mcp login' to re-authenticate."
                )

    async def disconnect(self) -> None:
        try:
            if self.client.is_connected():
                await self.client.disconnect()
        finally:
            self._release_session_lock()

    async def _run_read(self, label: str, factory):
        return await self._scheduler.run(
            "read",
            label,
            self.settings.tool_read_timeout_seconds,
            factory,
        )

    async def _dedupe_read_call(
        self,
        key: tuple[Any, ...],
        factory: Callable[[], Awaitable[T]],
    ) -> T:
        """Share only currently running identical read-only calls."""
        if self._read_inflight_dedupe_size <= 0:
            return await factory()

        normalized_key = tuple(self._normalize_cache_key_part(part) for part in key)
        run_without_dedupe = False
        async with self._read_inflight_lock:
            task = self._read_inflight_calls.get(normalized_key)
            if task is not None and task.done():
                del self._read_inflight_calls[normalized_key]
                task = None
            if task is not None:
                self._read_inflight_calls.move_to_end(normalized_key)
            else:
                self._prune_completed_read_calls()
                if len(self._read_inflight_calls) >= self._read_inflight_dedupe_size:
                    run_without_dedupe = True
                else:
                    task = asyncio.create_task(factory())
                    self._read_inflight_calls[normalized_key] = task
                    loop = asyncio.get_running_loop()
                    task.add_done_callback(
                        lambda completed, cache_key=normalized_key, event_loop=loop: event_loop.create_task(
                            self._forget_read_call(cache_key, completed)
                        )
                    )

        if run_without_dedupe:
            return await factory()
        return await asyncio.shield(task)

    def _prune_completed_read_calls(self) -> None:
        for key, task in list(self._read_inflight_calls.items()):
            if task.done():
                del self._read_inflight_calls[key]

    async def _forget_read_call(
        self,
        key: tuple[Any, ...],
        task: asyncio.Task[Any],
    ) -> None:
        async with self._read_inflight_lock:
            if self._read_inflight_calls.get(key) is task:
                del self._read_inflight_calls[key]

    def _transcript_cache_get(self, chat_id: int, message_id: int) -> str | None:
        if self._transcript_cache_size <= 0:
            return None
        key = (chat_id, message_id)
        transcript = self._transcript_cache.get(key)
        if transcript is None:
            return None
        self._transcript_cache.move_to_end(key)
        return transcript

    def _transcript_cache_set(
        self,
        chat_id: int,
        message_id: int,
        transcript: str,
    ) -> None:
        if self._transcript_cache_size <= 0:
            return
        key = (chat_id, message_id)
        self._transcript_cache[key] = transcript
        self._transcript_cache.move_to_end(key)
        while len(self._transcript_cache) > self._transcript_cache_size:
            self._transcript_cache.popitem(last=False)

    async def _run_write(self, label: str, factory):
        started_at = time.perf_counter()
        self._append_write_audit_event(label, "started", started_at)
        try:
            result = await self._scheduler.run(
                "write",
                label,
                self.settings.tool_write_timeout_seconds,
                factory,
            )
        except BaseException as exc:
            self._append_write_audit_event(label, "failed", started_at, error=exc)
            raise
        self._append_write_audit_event(label, "succeeded", started_at)
        return result

    def _append_write_audit_event(
        self,
        label: str,
        status: str,
        started_at: float,
        *,
        lane: str = "write",
        error: BaseException | None = None,
    ) -> None:
        if not self.settings.write_audit_enabled:
            return

        event: dict[str, Any] = {
            "event": "telegram_write",
            "operation": label,
            "status": status,
            "lane": lane,
            "event_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "duration_ms": round((time.perf_counter() - started_at) * 1000, 3),
        }
        if error is not None:
            event["error_type"] = type(error).__name__
            if isinstance(error, ToolContractError):
                event["error_code"] = error.code

        try:
            audit_path = Path(self.settings.write_audit_log_path)
            audit_path.parent.mkdir(parents=True, exist_ok=True)
            with audit_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(event, ensure_ascii=False) + "\n")
        except Exception as exc:
            log.warning(
                "telegram_write_audit_failed",
                operation=label,
                error=f"{type(exc).__name__}: {exc}",
            )

    async def _run_media(self, label: str, factory):
        return await self._scheduler.run(
            "media",
            label,
            self.settings.tool_media_timeout_seconds,
            factory,
        )

    async def _run_transcribe(self, label: str, factory):
        return await self._scheduler.run(
            "transcribe",
            label,
            self.settings.tool_transcribe_timeout_seconds,
            factory,
        )

    async def _run_enrich(self, label: str, factory):
        return await self._scheduler.run(
            "enrich",
            label,
            self.settings.tool_enrich_timeout_seconds,
            factory,
        )

    async def health_check(self) -> HealthInfo:
        connected = self.client.is_connected()
        authorized = False
        if connected:
            try:
                authorized = await self.client.is_user_authorized()
            except Exception:
                authorized = False
        from .runtime import get_runtime_report

        return HealthInfo(
            connected=connected,
            authorized=authorized,
            session_backend=self.settings.session_backend,
            entity_cache_size=len(self._entity_cache),
            download_dir=str(self.settings.download_dir),
            session_path=(
                str(self.settings.session_path)
                if self.settings.uses_file_session
                else None
            ),
            scheduler=self._scheduler.snapshot(),
            runtime_stats=self._runtime_stats_snapshot(),
            **get_runtime_report(),
        )

    async def doctor_check(self) -> DoctorInfo:
        warnings: list[str] = []
        checks: dict[str, str] = {}
        transport = self.settings.mcp_transport.strip().lower()
        checks["transport"] = transport
        runtime_fields: dict[str, str | int | None] = {
            "host": None,
            "port": None,
            "http_path": None,
            "endpoint_url": None,
        }
        if transport != "stdio":
            runtime_fields = {
                "host": self.settings.mcp_host,
                "port": self.settings.mcp_port,
                "http_path": self.settings.mcp_http_path,
                "endpoint_url": f"http://{self.settings.mcp_host}:{self.settings.mcp_port}{self.settings.mcp_http_path}",
            }

        try:
            self.settings.ensure_dirs()
            checks["download_dir"] = "ok"
            cleanup = estimate_download_cleanup(
                Path(self.settings.download_dir),
                self.settings.download_retention_days,
            )
            download_cleanup = cleanup.to_dict()
            checks["download_cleanup"] = "enabled" if cleanup.enabled else "disabled"
        except Exception as exc:
            checks["download_dir"] = "error"
            download_cleanup = None
            warnings.append(f"download_dir: {type(exc).__name__}: {exc}")

        if self.settings.uses_file_session:
            checks["session_backend"] = "sqlite"
            checks["session_dir"] = (
                "ok" if self.settings.session_dir.exists() else "missing"
            )
            checks["session_lock"] = (
                "held" if self._session_lock is not None else "available"
            )
        else:
            checks["session_backend"] = "string"
            checks["session_dir"] = "disabled"
            checks["session_lock"] = "disabled"

        checks["connection"] = "connected" if self.client.is_connected() else "idle"
        checks["scheduler"] = "ok"

        status = "ok"
        if any(value in {"error", "missing"} for value in checks.values()):
            status = "warn"
        if warnings:
            status = "warn"

        return DoctorInfo(
            status=status,
            transport=transport,
            session_backend=self.settings.session_backend,
            checks=checks,
            warnings=warnings,
            download_cleanup=download_cleanup,
            scheduler=self._scheduler.snapshot(),
            runtime_stats=self._runtime_stats_snapshot(),
            **runtime_fields,
        )

    def _acquire_session_lock(self) -> None:
        if not self.settings.uses_file_session:
            return
        if self._session_lock is None:
            self._session_lock = FileSessionLock(
                self.settings.session_dir / "session.lock"
            )
        self._session_lock.acquire()

    def _release_session_lock(self) -> None:
        if self._session_lock is None:
            return
        self._session_lock.release()

    def _cache_lookup_keys(self, chat: str | int) -> list[str | int]:
        keys: list[str | int] = []
        seen: set[str | int] = set()

        def add(key: str | int | None) -> None:
            if key is None:
                return
            if isinstance(key, str):
                key = key.strip()
                if not key:
                    return
            if key in seen:
                return
            seen.add(key)
            keys.append(key)

        add(chat)
        if isinstance(chat, int):
            add(str(chat))
            return keys

        normalized = chat.strip()
        add(normalized)
        add(normalized.lower())
        if normalized.startswith("@"):
            bare_username = normalized[1:]
            add(bare_username)
            add(bare_username.lower())
        try:
            numeric_id = int(normalized)
        except (ValueError, TypeError):
            numeric_id = None
        add(numeric_id)
        if numeric_id is not None:
            add(str(numeric_id))
        return keys

    def _entity_cache_keys(self, chat: str | int, entity: Any) -> list[str | int]:
        keys = self._cache_lookup_keys(chat)

        entity_id = getattr(entity, "id", None)
        if isinstance(entity_id, int):
            keys.extend(
                key
                for key in (entity_id, str(entity_id))
                if key not in keys
            )

        username = getattr(entity, "username", None)
        if isinstance(username, str):
            normalized_username = username.strip().lstrip("@")
            if normalized_username:
                for key in (
                    normalized_username,
                    normalized_username.lower(),
                    f"@{normalized_username}",
                    f"@{normalized_username.lower()}",
                ):
                    if key not in keys:
                        keys.append(key)

        return keys

    def _cache_remember(
        self,
        cache: OrderedDict[str | int, Any],
        *,
        keys: list[str | int],
        value: Any,
    ) -> None:
        for key in keys:
            cache[key] = value
            cache.move_to_end(key)

        while len(cache) > self.settings.resolve_cache_size:
            evicted_key, _ = cache.popitem(last=False)
            if cache is self._entity_cache:
                self._input_entity_cache.pop(evicted_key, None)

    def _get_cached_value(
        self,
        cache: OrderedDict[str | int, Any],
        chat: str | int,
    ) -> Any | None:
        for key in self._cache_lookup_keys(chat):
            if key not in cache:
                continue
            cache.move_to_end(key)
            return cache[key]
        return None

    def _remember_dialog_ref_entity(self, dialog_ref: str, entity: Any) -> None:
        self._dialog_ref_entity_cache[dialog_ref] = entity
        self._dialog_ref_entity_cache.move_to_end(dialog_ref)
        while len(self._dialog_ref_entity_cache) > self.settings.resolve_cache_size:
            evicted_key, _ = self._dialog_ref_entity_cache.popitem(last=False)
            self._dialog_ref_input_entity_cache.pop(evicted_key, None)

    def _remember_dialog_ref_input_entity(self, dialog_ref: str, input_entity: Any) -> None:
        self._dialog_ref_input_entity_cache[dialog_ref] = input_entity
        self._dialog_ref_input_entity_cache.move_to_end(dialog_ref)
        while len(self._dialog_ref_input_entity_cache) > self.settings.resolve_cache_size:
            self._dialog_ref_input_entity_cache.popitem(last=False)

    async def _resolve_entity(self, chat: str | int):
        if not isinstance(chat, (str, int)):
            return chat

        if isinstance(chat, str):
            normalized = chat.strip()
            if normalized.startswith("tg://dialog/"):
                cached_dialog_entity = self._dialog_ref_entity_cache.get(normalized)
                if cached_dialog_entity is None:
                    raise ToolContractError(
                        "dialog_not_found",
                        "dialog_ref is unknown in this session",
                    )
                self._dialog_ref_entity_cache.move_to_end(normalized)
                return cached_dialog_entity

        cached_entity = self._get_cached_value(self._entity_cache, chat)
        if cached_entity is not None:
            return cached_entity

        try:
            entity = await resolve_entity(self.client, chat)
        except ValueError as exc:
            raise ToolContractError("dialog_not_found", str(exc)) from None
        self._cache_remember(
            self._entity_cache,
            keys=self._entity_cache_keys(chat, entity),
            value=entity,
        )

        return entity

    async def _resolve_input_entity(self, chat: str | int):
        if not isinstance(chat, (str, int)):
            return await self.client.get_input_entity(chat)

        if isinstance(chat, str):
            normalized = chat.strip()
            if normalized.startswith("tg://dialog/"):
                cached_dialog_input = self._dialog_ref_input_entity_cache.get(normalized)
                if cached_dialog_input is not None:
                    self._dialog_ref_input_entity_cache.move_to_end(normalized)
                    return cached_dialog_input

                entity = await self._resolve_entity(normalized)
                input_entity = await self.client.get_input_entity(entity)
                self._remember_dialog_ref_input_entity(normalized, input_entity)
                return input_entity

        cached_input_entity = self._get_cached_value(self._input_entity_cache, chat)
        if cached_input_entity is not None:
            return cached_input_entity

        entity = await self._resolve_entity(chat)
        input_entity = await self.client.get_input_entity(entity)
        self._cache_remember(
            self._input_entity_cache,
            keys=self._entity_cache_keys(chat, entity),
            value=input_entity,
        )
        return input_entity

    # ── Result cache ──

    def _cache_get(self, key: str, *, ttl: int | None = None) -> Any | None:
        """Return cached value if TTL is enabled and entry is fresh, else None."""
        effective_ttl = self._cache_ttl if ttl is None else ttl
        if effective_ttl <= 0 or self._result_cache_size <= 0:
            return None
        entry = self._result_cache.get(key)
        if entry is None:
            self._record_cache_access_stat(key, hit=False)
            self._emit_cache_event(
                "telegram_result_cache_miss",
                key=key,
                reason="missing",
            )
            return None
        ts, value = entry
        if time.monotonic() - ts > effective_ttl:
            del self._result_cache[key]
            self._record_cache_access_stat(key, hit=False)
            self._emit_cache_event(
                "telegram_result_cache_miss",
                key=key,
                reason="expired",
            )
            return None
        self._result_cache.move_to_end(key)
        item_count = len(value) if isinstance(value, list) else None
        self._record_cache_access_stat(key, hit=True)
        self._emit_cache_event(
            "telegram_result_cache_hit",
            key=key,
            item_count=item_count,
        )
        return value

    def _cache_set(self, key: str, value: Any) -> None:
        if self._cache_ttl <= 0 or self._result_cache_size <= 0:
            return
        self._result_cache[key] = (time.monotonic(), value)
        self._result_cache.move_to_end(key)
        while len(self._result_cache) > self._result_cache_size:
            self._result_cache.popitem(last=False)
        item_count = len(value) if isinstance(value, list) else None
        self._emit_cache_event(
            "telegram_result_cache_store",
            key=key,
            item_count=item_count,
        )

    def invalidate_cache(self, prefix: str | None = None) -> None:
        """Drop cached results. If prefix given, only keys starting with it."""
        if prefix is None:
            removed_count = len(self._result_cache)
            self._result_cache.clear()
        else:
            keys = [k for k in self._result_cache if k.startswith(prefix)]
            for k in keys:
                del self._result_cache[k]
            removed_count = len(keys)
        self._emit_diagnostic(
            "telegram_result_cache_invalidate",
            prefix=prefix or "*",
            removed_count=removed_count,
            cache_size=len(self._result_cache),
        )

    def _invalidate_chat_list_cache(self) -> None:
        self.invalidate_cache("list_chats")

    def _dialog_read_cache_get(self, key: str) -> Any | None:
        return self._cache_get(key, ttl=self._dialog_read_cache_ttl)

    def _dialog_read_cache_set(self, key: str, value: Any) -> None:
        if self._dialog_read_cache_ttl <= 0:
            return
        self._cache_set(key, value)

    def _invalidate_dialog_read_cache(self) -> None:
        self.invalidate_cache("dialog_read:")
        self.invalidate_cache("dialog_search:")

    def _invalidate_after_dialog_write(self) -> None:
        self._invalidate_dialog_read_cache()
        self._invalidate_chat_list_cache()
        self._increment_runtime_stat("cache_invalidated_after_write")

    def _normalize_cache_key_part(self, value: Any) -> Any:
        if isinstance(value, str):
            normalized = value.strip()
            if normalized.startswith("@"):
                return normalized.lower()
            return normalized
        if isinstance(value, list | tuple):
            return tuple(self._normalize_cache_key_part(item) for item in value)
        if isinstance(value, dict):
            return tuple(
                (str(key), self._normalize_cache_key_part(item))
                for key, item in sorted(value.items(), key=lambda entry: str(entry[0]))
            )
        return value

    def _make_result_cache_key(self, prefix: str, *parts: Any) -> str:
        normalized = tuple(self._normalize_cache_key_part(part) for part in parts)
        return f"{prefix}:{json.dumps(normalized, ensure_ascii=False, sort_keys=True, default=str)}"

    def _validate_non_negative(self, label: str, value: int) -> None:
        if value < 0:
            raise ToolContractError(
                "invalid_pagination",
                f"{label} must be greater than or equal to 0",
            )
