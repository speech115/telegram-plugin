# TDLib Large-Media-Download Graduation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Graduate the TDLib media-download POC into a narrowly-scoped production capability — TDLib as an auto-routed backend for large media downloads on the `main` account only, with every failure mode falling back to the existing Telethon path.

**Architecture:** `download_post()` (`mcp/src/telegram_mcp/download_post.py`) keeps its existing Telethon connect/resolve-entity/resolve-message flow unchanged. After the message is resolved, a pure routing-decision function decides (account, enabled flag, content type, size vs. threshold) whether to attempt TDLib. On a route decision, a new `tdlib_download.py` module opens a fresh in-process TDLib client against an already-authorized on-disk session, downloads the file, and hands the path back; any failure — including a session-lock timeout — falls back to the Telethon `client`/`msg` the function already has open, so no extra Telegram round-trip is ever spent deciding or falling back.

**Tech Stack:** Python ≥3.12, Telethon (existing), `pytdbot`/`tdjson` (new, optional extra), `fcntl`-based advisory locking (existing pattern, extended), `unittest`-based test suite (existing convention — this repo runs tests with `unittest discover`, not `pytest`).

## Global Constraints

- TDLib is **not** a general runtime: reads, search, sends, and all other Telegram operations stay on Telethon, unchanged. (spec Non-Goals)
- Only the `main` account is eligible for TDLib routing. No other account gets TDLib in this iteration. (spec Non-Goals)
- No persistent TDLib daemon — every download gets a fresh, in-process TDLib client reconnecting to an already-authorized on-disk session, then tears down. (spec Non-Goals)
- This does not touch the MCP tool surface (`download_media_batch`, `download_dialog_media`). TDLib routing applies only to `download_post()` / `tg download`. (spec Non-Goals)
- `pytdbot`/`tdjson` are an **optional** extras group (`telegram-mcp[tdlib]`), never a hard dependency. The `pytdbot` import is lazy, inside functions, guarded by `TELEGRAM_TDLIB_ENABLED` — nothing in the rest of the package imports `tdlib_download.py` at module load time (i.e. `download_post.py`'s top-level imports must not include `tdlib_download`; import it locally inside the function that needs it). (spec Dependencies)
- `TELEGRAM_TDLIB_ENABLED` defaults to unset/`false` — the capability stays off until an operator turns it on explicitly. (spec Configuration)
- Isolation marker for the TDLib files directory stays `.telegram-mcp` (not `.telegram-mcp-tdlib`) — same guard as the POC, ported verbatim. (spec Components)
- Every failure mode on the TDLib path falls back to Telethon using the connection/message already fetched during routing — never a hard failure introduced by this change. (spec Error Handling / Fallback)
- Test baseline: `cd mcp && TELEGRAM_API_ID=1 TELEGRAM_API_HASH=hash PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p 'test_*.py'` currently passes 379/379. Every task must keep this command green.

---

## File map

**Create**

- `mcp/docs/superpowers/plans/2026-07-01-tdlib-large-media-download-implementation.md` (this file)
- `mcp/src/telegram_mcp/tdlib_download.py`
- `mcp/tests/test_tdlib_download.py`
- `mcp/scripts/tdlib_login.py`

**Modify**

- `mcp/src/telegram_mcp/locking.py`
- `mcp/tests/test_locking.py`
- `mcp/src/telegram_mcp/download_post.py`
- `mcp/tests/test_download_post.py`
- `mcp/pyproject.toml`
- `mcp/.env.example`
- `docs/operator-workflows.md`

**Keep untouched**

- `mcp/src/telegram_mcp/tools/media_tools.py` and the MCP `download_media_batch`/`download_dialog_media` tools
- `experiments/tdlib-media-poc/` (POC stays as historical reference, not imported from production code)
- Everything about non-`main` accounts

---

## Task 1: Timeout-bounded lock acquisition in `locking.py`

**Files:**
- Modify: `mcp/src/telegram_mcp/locking.py`
- Test: `mcp/tests/test_locking.py`

**Interfaces:**
- Consumes: existing `FileSessionLock` class (`acquire()` raises `SessionLockError`, `release()`).
- Produces: `try_acquire_with_timeout(lock: FileSessionLock, *, timeout_seconds: float = 5.0, poll_interval_seconds: float = 0.2) -> bool` — `True` if acquired (caller must `release()` later), `False` if the timeout elapsed without acquiring (caller falls back, does **not** call `release()`). Task 2 imports this from `telegram_mcp.locking`.

- [ ] **Step 1: Write the failing test**

Add to `mcp/tests/test_locking.py` (append to the existing `LockingTests` class):

```python
    def test_try_acquire_with_timeout_returns_false_when_held(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock_path = Path(tmp) / "telegram.lock"

            holder = FileSessionLock(lock_path)
            holder.acquire()
            try:
                waiter = FileSessionLock(lock_path)
                acquired = try_acquire_with_timeout(
                    waiter, timeout_seconds=0.3, poll_interval_seconds=0.1
                )
                self.assertFalse(acquired)
            finally:
                holder.release()

    def test_try_acquire_with_timeout_succeeds_once_free(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock_path = Path(tmp) / "telegram.lock"

            lock = FileSessionLock(lock_path)
            acquired = try_acquire_with_timeout(lock, timeout_seconds=0.3)
            try:
                self.assertTrue(acquired)
            finally:
                lock.release()
```

Update the import line at the top of `mcp/tests/test_locking.py`:

```python
from telegram_mcp.locking import FileSessionLock, SessionLockError, try_acquire_with_timeout
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd mcp && PYTHONPATH=src .venv/bin/python -m unittest tests.test_locking -v`
Expected: FAIL with `ImportError: cannot import name 'try_acquire_with_timeout'`

- [ ] **Step 3: Implement `try_acquire_with_timeout`**

In `mcp/src/telegram_mcp/locking.py`, add `import time` to the top-level imports (alongside the existing `import fcntl` / `import os`), and append this function after the `FileSessionLock` class:

```python
def try_acquire_with_timeout(
    lock: FileSessionLock,
    *,
    timeout_seconds: float = 5.0,
    poll_interval_seconds: float = 0.2,
) -> bool:
    """Retry ``lock.acquire()`` until it succeeds or ``timeout_seconds`` elapse.

    Returns True if acquired (caller owns the lock and must call release()).
    Returns False if the timeout elapsed without acquiring — the caller
    should fall back rather than treat this as an error.
    """
    deadline = time.monotonic() + timeout_seconds
    while True:
        try:
            lock.acquire()
            return True
        except SessionLockError:
            if time.monotonic() >= deadline:
                return False
            time.sleep(poll_interval_seconds)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd mcp && PYTHONPATH=src .venv/bin/python -m unittest tests.test_locking -v`
Expected: PASS (3 tests: the existing one plus the 2 new ones)

- [ ] **Step 5: Commit**

```bash
git add mcp/src/telegram_mcp/locking.py mcp/tests/test_locking.py
git commit -m "feat: add timeout-bounded lock acquisition for TDLib session locking"
```

---

## Task 2: `tdlib_download.py` — routing decision, isolation guard, TDLib client wiring

**Files:**
- Create: `mcp/src/telegram_mcp/tdlib_download.py`
- Test: `mcp/tests/test_tdlib_download.py`
- Modify: `mcp/pyproject.toml` (optional extras group)
- Modify: `mcp/.env.example` (new env vars)

**Interfaces:**
- Consumes: `telegram_mcp.locking.FileSessionLock`, `telegram_mcp.locking.try_acquire_with_timeout` (Task 1).
- Produces (consumed by Task 3):
  - `SUPPORTED_CONTENT_KINDS: frozenset[str]` = `{"video", "document", "photo", "audio"}`
  - `should_route_to_tdlib(*, account: str, tdlib_enabled: bool, content_kind: str | None, media_size_bytes: int | None, threshold_mb: float) -> bool`
  - `async def download_via_tdlib(*, link: str, session_dir: Path) -> Path` — raises `RuntimeError` (or a subclass) on any failure; returns the local downloaded file path on success.

- [ ] **Step 1: Write the failing tests for the pure, pytdbot-free logic**

Create `mcp/tests/test_tdlib_download.py`:

```python
import importlib.util
import unittest

from telegram_mcp.tdlib_download import assert_isolated_from_telethon, should_route_to_tdlib

PYTDBOT_AVAILABLE = importlib.util.find_spec("pytdbot") is not None


class ShouldRouteToTdlibTests(unittest.TestCase):
    def test_routes_when_all_conditions_met(self):
        self.assertTrue(
            should_route_to_tdlib(
                account="main",
                tdlib_enabled=True,
                content_kind="video",
                media_size_bytes=30 * 1024 * 1024,
                threshold_mb=20,
            )
        )

    def test_rejects_non_main_account(self):
        self.assertFalse(
            should_route_to_tdlib(
                account="pl",
                tdlib_enabled=True,
                content_kind="video",
                media_size_bytes=30 * 1024 * 1024,
                threshold_mb=20,
            )
        )

    def test_rejects_when_disabled(self):
        self.assertFalse(
            should_route_to_tdlib(
                account="main",
                tdlib_enabled=False,
                content_kind="video",
                media_size_bytes=30 * 1024 * 1024,
                threshold_mb=20,
            )
        )

    def test_rejects_unsupported_content_kind(self):
        self.assertFalse(
            should_route_to_tdlib(
                account="main",
                tdlib_enabled=True,
                content_kind=None,
                media_size_bytes=30 * 1024 * 1024,
                threshold_mb=20,
            )
        )

    def test_rejects_below_threshold(self):
        self.assertFalse(
            should_route_to_tdlib(
                account="main",
                tdlib_enabled=True,
                content_kind="video",
                media_size_bytes=1 * 1024 * 1024,
                threshold_mb=20,
            )
        )

    def test_rejects_unknown_size(self):
        self.assertFalse(
            should_route_to_tdlib(
                account="main",
                tdlib_enabled=True,
                content_kind="video",
                media_size_bytes=None,
                threshold_mb=20,
            )
        )


class AssertIsolatedFromTelethonTests(unittest.TestCase):
    def test_rejects_telethon_session_tree(self):
        with self.assertRaises(ValueError):
            assert_isolated_from_telethon("/Users/x/.telegram-mcp/main")

    def test_accepts_isolated_directory(self):
        assert_isolated_from_telethon("/Users/x/.telegram-mcp-tdlib/main")


@unittest.skipUnless(PYTDBOT_AVAILABLE, "pytdbot not installed (optional [tdlib] extra)")
class PytdbotDependentTests(unittest.TestCase):
    def test_raise_if_error_passes_through_non_error_result(self):
        from telegram_mcp.tdlib_download import raise_if_error

        self.assertEqual(raise_if_error("some value"), "some value")

    def test_raise_if_error_raises_on_pytdbot_error(self):
        import pytdbot

        from telegram_mcp.tdlib_download import raise_if_error

        error = pytdbot.types.Error(code=400, message="MESSAGE_ID_INVALID")
        with self.assertRaisesRegex(RuntimeError, "MESSAGE_ID_INVALID"):
            raise_if_error(error)

    def test_extract_file_id_from_message_video(self):
        import pytdbot

        from telegram_mcp.tdlib_download import extract_file_id_from_message

        message = pytdbot.types.Message(
            content=pytdbot.types.MessageVideo(
                video=pytdbot.types.Video(video=pytdbot.types.File(id=555, size=52_428_800))
            )
        )
        self.assertEqual(extract_file_id_from_message(message), 555)

    def test_extract_file_id_from_message_unsupported_type(self):
        import pytdbot

        from telegram_mcp.tdlib_download import extract_file_id_from_message

        message = pytdbot.types.Message(content=pytdbot.types.MessageText())
        with self.assertRaisesRegex(ValueError, "unsupported message content type"):
            extract_file_id_from_message(message)

    def test_build_client_rejects_telethon_session_tree(self):
        from telegram_mcp.tdlib_download import build_client

        with self.assertRaises(ValueError):
            build_client(
                api_id=1,
                api_hash="hash",
                files_directory="/Users/x/.telegram-mcp/main",
            )


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd mcp && PYTHONPATH=src .venv/bin/python -m unittest tests.test_tdlib_download -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'telegram_mcp.tdlib_download'`

- [ ] **Step 3: Declare the optional dependency and env vars**

In `mcp/pyproject.toml`, add an `[project.optional-dependencies]` table right after the existing `dependencies` list:

```toml
[project.optional-dependencies]
tdlib = [
    "Pytdbot>=0.10.1",
    "tdjson>=1.8.65",
]
```

In `mcp/.env.example`, add this block right after the `TELEGRAM_DOWNLOAD_*` group (after the `TELEGRAM_DOWNLOAD_CLEANUP_INTERVAL_SECONDS` line):

```
# Optional: route large media downloads on the main account through TDLib.
# Requires `pip install -e ".[tdlib]"` and a one-time `mcp/scripts/tdlib_login.py` run.
# TELEGRAM_TDLIB_ENABLED=false
# TELEGRAM_TDLIB_SESSION_DIR=~/.telegram-mcp-tdlib/main
# TELEGRAM_TDLIB_DOWNLOAD_THRESHOLD_MB=20
```

- [ ] **Step 4: Implement `tdlib_download.py`**

Create `mcp/src/telegram_mcp/tdlib_download.py`:

```python
"""TDLib backend for large media downloads on the `main` account only.

Graduated from the isolated POC (experiments/tdlib-media-poc/) per
mcp/docs/superpowers/specs/2026-07-01-tdlib-large-media-download-design.md.
`pytdbot` is an optional dependency (`telegram-mcp[tdlib]`) — every function
here that needs it imports it lazily, so importing this module never
requires pytdbot to be installed.
"""

from __future__ import annotations

import os
from pathlib import Path

from .locking import FileSessionLock, try_acquire_with_timeout

TELETHON_SESSION_DIR_MARKER = ".telegram-mcp"

SUPPORTED_CONTENT_KINDS = frozenset({"video", "document", "photo", "audio"})


class TdlibDownloadError(RuntimeError):
    """Raised for any TDLib download failure; callers should fall back to Telethon."""


def assert_isolated_from_telethon(files_directory: str) -> None:
    if TELETHON_SESSION_DIR_MARKER in files_directory:
        raise ValueError(
            f"files_directory must not overlap the Telethon session tree "
            f"(found {TELETHON_SESSION_DIR_MARKER!r})"
        )


def build_client(
    api_id: int,
    api_hash: str,
    files_directory: str,
    database_encryption_key: str = "telegram-mcp-tdlib",
):
    assert_isolated_from_telethon(files_directory)
    import pytdbot

    return pytdbot.Client(
        api_id=api_id,
        api_hash=api_hash,
        files_directory=files_directory,
        database_encryption_key=database_encryption_key,
        use_file_database=True,
        use_chat_info_database=False,
        use_message_database=False,
    )


def raise_if_error(result):
    import pytdbot

    if isinstance(result, pytdbot.types.Error):
        raise TdlibDownloadError(f"TDLib error {result['code']}: {result['message']}")
    return result


def extract_file_id_from_message(message) -> int:
    content = message["content"]
    content_type = content.getType()
    if content_type == "messageVideo":
        return content["video"]["video"]["id"]
    if content_type == "messageDocument":
        return content["document"]["document"]["id"]
    if content_type == "messagePhoto":
        sizes = content["photo"]["sizes"]
        return sizes[-1]["photo"]["id"]
    if content_type == "messageAudio":
        return content["audio"]["audio"]["id"]
    raise ValueError(f"unsupported message content type for download: {content_type!r}")


def should_route_to_tdlib(
    *,
    account: str,
    tdlib_enabled: bool,
    content_kind: str | None,
    media_size_bytes: int | None,
    threshold_mb: float,
) -> bool:
    if account != "main":
        return False
    if not tdlib_enabled:
        return False
    if content_kind not in SUPPORTED_CONTENT_KINDS:
        return False
    if media_size_bytes is None:
        return False
    return media_size_bytes >= threshold_mb * 1024 * 1024


async def download_via_tdlib(*, link: str, session_dir: Path) -> Path:
    """Resolve `link` via TDLib and download it fully. Returns the local file
    path on success. Raises TdlibDownloadError on any failure (lock timeout,
    TDLib error, incomplete download) — the caller decides to fall back."""
    lock = FileSessionLock(session_dir / "download.lock")
    if not try_acquire_with_timeout(lock, timeout_seconds=5.0):
        raise TdlibDownloadError("could not acquire TDLib session lock within 5s")

    try:
        client = build_client(
            api_id=int(os.environ["TELEGRAM_API_ID"]),
            api_hash=os.environ["TELEGRAM_API_HASH"],
            files_directory=str(session_dir),
        )
        await client.start()
        try:
            link_info = raise_if_error(await client.getMessageLinkInfo(url=link))
            message = raise_if_error(
                await client.getMessage(
                    chat_id=link_info["chat_id"], message_id=link_info["message"]["id"]
                )
            )
            file_id = extract_file_id_from_message(message)
            result = raise_if_error(
                await client.downloadFile(
                    file_id=file_id, priority=1, synchronous=True, offset=0, limit=0
                )
            )
            local = result["local"]
            if not local or not bool(local["is_downloading_completed"]):
                raise TdlibDownloadError("TDLib download did not complete")
            return Path(local["path"])
        finally:
            await client.stop()
    finally:
        lock.release()
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd mcp && PYTHONPATH=src .venv/bin/python -m unittest tests.test_tdlib_download -v`
Expected: PASS — `ShouldRouteToTdlibTests` (6) and `AssertIsolatedFromTelethonTests` (2) run and pass; `PytdbotDependentTests` (5) show as `skipped` since `pytdbot` isn't installed in the portable dev/CI venv.

- [ ] **Step 6: Run the full suite to confirm no regressions**

Run: `cd mcp && TELEGRAM_API_ID=1 TELEGRAM_API_HASH=hash PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p 'test_*.py'`
Expected: `OK` (387 tests: 379 baseline + 8 new non-skipped)

- [ ] **Step 7: Commit**

```bash
git add mcp/src/telegram_mcp/tdlib_download.py mcp/tests/test_tdlib_download.py mcp/pyproject.toml mcp/.env.example
git commit -m "feat: add tdlib_download module with routing decision and optional pytdbot backend"
```

---

## Task 3: Wire TDLib routing and fallback into `download_post()`

**Files:**
- Modify: `mcp/src/telegram_mcp/download_post.py`
- Test: `mcp/tests/test_download_post.py`

**Interfaces:**
- Consumes: `telegram_mcp.tdlib_download.should_route_to_tdlib`, `telegram_mcp.tdlib_download.download_via_tdlib` (Task 2), `telegram_mcp.telemetry.record_telemetry` (existing — signature `record_telemetry(event: str, **fields) -> None`, never raises).
- Produces: `_telethon_media_kind(msg) -> str | None`, `_telethon_media_size_bytes(msg) -> int | None` — new pure helpers, unit-tested directly. `download_post()`'s returned dict gains no new keys (existing shape preserved); backend selection is internal + telemetry-only.

- [ ] **Step 1: Write the failing tests for the new pure helpers**

Add to `mcp/tests/test_download_post.py`, in a new test class (append before the `if __name__ == "__main__":` line), and add the two new names to the existing import line:

```python
from telegram_mcp.download_post import (
    ParsedLink,
    _ext_from_message,
    _telethon_media_kind,
    _telethon_media_size_bytes,
    parse_post_link,
)
```

```python
class TelethonMediaKindTests(unittest.TestCase):
    def test_photo_is_photo_kind(self):
        msg = SimpleNamespace(media=SimpleNamespace(document=None, photo=object()))
        self.assertEqual(_telethon_media_kind(msg), "photo")

    def test_video_mime_is_video_kind(self):
        doc = SimpleNamespace(attributes=[], mime_type="video/mp4", size=123)
        msg = SimpleNamespace(media=SimpleNamespace(document=doc, photo=None))
        self.assertEqual(_telethon_media_kind(msg), "video")

    def test_audio_mime_is_audio_kind(self):
        doc = SimpleNamespace(attributes=[], mime_type="audio/mpeg", size=123)
        msg = SimpleNamespace(media=SimpleNamespace(document=doc, photo=None))
        self.assertEqual(_telethon_media_kind(msg), "audio")

    def test_other_document_mime_is_document_kind(self):
        doc = SimpleNamespace(attributes=[], mime_type="application/pdf", size=123)
        msg = SimpleNamespace(media=SimpleNamespace(document=doc, photo=None))
        self.assertEqual(_telethon_media_kind(msg), "document")

    def test_no_media_is_unsupported(self):
        msg = SimpleNamespace(media=None)
        self.assertIsNone(_telethon_media_kind(msg))


class TelethonMediaSizeBytesTests(unittest.TestCase):
    def test_document_size(self):
        doc = SimpleNamespace(size=123456)
        msg = SimpleNamespace(media=SimpleNamespace(document=doc, photo=None))
        self.assertEqual(_telethon_media_size_bytes(msg), 123456)

    def test_photo_largest_size(self):
        sizes = [SimpleNamespace(size=100), SimpleNamespace(size=9000)]
        photo = SimpleNamespace(sizes=sizes)
        msg = SimpleNamespace(media=SimpleNamespace(document=None, photo=photo))
        self.assertEqual(_telethon_media_size_bytes(msg), 9000)

    def test_no_media_is_none(self):
        msg = SimpleNamespace(media=None)
        self.assertIsNone(_telethon_media_size_bytes(msg))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd mcp && PYTHONPATH=src .venv/bin/python -m unittest tests.test_download_post -v`
Expected: FAIL with `ImportError: cannot import name '_telethon_media_kind'`

- [ ] **Step 3: Implement the two helpers and wire routing/fallback**

In `mcp/src/telegram_mcp/download_post.py`, add these two functions right after `_ext_from_message` (same file, same style):

```python
def _telethon_media_kind(msg) -> str | None:
    media = getattr(msg, "media", None)
    if media is None:
        return None
    if getattr(media, "photo", None) is not None:
        return "photo"
    doc = getattr(media, "document", None)
    if doc is None:
        return None
    mime = getattr(doc, "mime_type", "") or ""
    if mime.startswith("video/"):
        return "video"
    if mime.startswith("audio/"):
        return "audio"
    return "document"


def _telethon_media_size_bytes(msg) -> int | None:
    media = getattr(msg, "media", None)
    if media is None:
        return None
    photo = getattr(media, "photo", None)
    if photo is not None:
        sizes = getattr(photo, "sizes", None) or []
        if not sizes:
            return None
        return max(getattr(s, "size", 0) for s in sizes)
    doc = getattr(media, "document", None)
    if doc is not None:
        return getattr(doc, "size", None)
    return None
```

Add the telemetry import to the top-level imports (alongside the existing `.mcp_http_client` import):

```python
from .telemetry import record_telemetry
```

Then, in `download_post()`, replace this block:

```python
        out = dest_dir / f"{parsed.label}_{parsed.message_id}{_ext_from_message(msg)}"
        progress = None if quiet else _make_progress()
        saved = await client.download_media(msg, file=str(out), progress_callback=progress)
```

with:

```python
        out = dest_dir / f"{parsed.label}_{parsed.message_id}{_ext_from_message(msg)}"

        from . import tdlib_download  # lazy: keeps pytdbot fully optional at module load time

        tdlib_enabled = os.environ.get("TELEGRAM_TDLIB_ENABLED", "false").strip().lower() == "true"
        threshold_mb = float(os.environ.get("TELEGRAM_TDLIB_DOWNLOAD_THRESHOLD_MB", "20"))
        route_to_tdlib = tdlib_download.should_route_to_tdlib(
            account=account,
            tdlib_enabled=tdlib_enabled,
            content_kind=_telethon_media_kind(msg),
            media_size_bytes=_telethon_media_size_bytes(msg),
            threshold_mb=threshold_mb,
        )

        tdlib_backend_used = False
        fallback_reason: str | None = None
        saved: str | None = None

        if route_to_tdlib:
            session_dir = Path(
                os.environ.get("TELEGRAM_TDLIB_SESSION_DIR", "~/.telegram-mcp-tdlib/main")
            ).expanduser()
            try:
                tdlib_path = await tdlib_download.download_via_tdlib(link=link, session_dir=session_dir)
                shutil.copy2(tdlib_path, out)
                saved = str(out)
                tdlib_backend_used = True
            except Exception as exc:  # noqa: BLE001 - any TDLib failure falls back to Telethon
                fallback_reason = str(exc)

        if saved is None:
            progress = None if quiet else _make_progress()
            saved = await client.download_media(msg, file=str(out), progress_callback=progress)

        record_telemetry(
            "download_post_backend",
            backend="tdlib" if tdlib_backend_used else "telethon",
            account=account,
            route_attempted=route_to_tdlib,
            fallback_reason=fallback_reason,
        )
```

Note: `saved` was previously assigned unconditionally by the last line of the replaced block; it is now assigned either by the TDLib branch or the Telethon fallback branch, so the function's final `saved_path = Path(saved) if saved else out` line below stays correct unchanged.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd mcp && PYTHONPATH=src .venv/bin/python -m unittest tests.test_download_post -v`
Expected: PASS (13 tests: 6 existing + 5 kind tests + 3 size tests... run and check actual count in output; all green)

- [ ] **Step 5: Run the full suite to confirm no regressions**

Run: `cd mcp && TELEGRAM_API_ID=1 TELEGRAM_API_HASH=hash PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p 'test_*.py'`
Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git add mcp/src/telegram_mcp/download_post.py mcp/tests/test_download_post.py
git commit -m "feat: route large main-account downloads through TDLib with Telethon fallback"
```

---

## Task 4: Production TDLib login script

**Files:**
- Create: `mcp/scripts/tdlib_login.py`

**Interfaces:**
- Consumes: `telegram_mcp.tdlib_download.build_client`, `telegram_mcp.tdlib_download.raise_if_error` (Task 2).
- Produces: a standalone CLI (`--phone`/`--code`/`--password`), no importable interface consumed by later tasks.

- [ ] **Step 1: Port the script**

Create `mcp/scripts/tdlib_login.py` (adapted from `experiments/tdlib-media-poc/benchmark/login_tdlib.py`, pointed at the production session dir and reusing `telegram_mcp.tdlib_download` instead of duplicating `build_client`/`raise_if_error`):

```python
"""Interactive-by-invocation TDLib login for the production `main`-account
media-download backend.

pytdbot's Client.start() only auto-drives the authorization state machine for
bot-token logins. For a real user account it does nothing at
authorizationStateWaitPhoneNumber, so this script drives the state machine
manually across multiple invocations, since a live phone/SMS code can't be fed
into a blocking input() call from outside a real TTY:

    PYTHONPATH=src .venv/bin/python scripts/tdlib_login.py --phone +15551234567
    # (Telegram sends a login code to your other active sessions)
    PYTHONPATH=src .venv/bin/python scripts/tdlib_login.py --code 12345
    # (only if the account has 2FA enabled)
    PYTHONPATH=src .venv/bin/python scripts/tdlib_login.py --password ...

Each invocation reconnects to the same persistent session under
TELEGRAM_TDLIB_SESSION_DIR (default ~/.telegram-mcp-tdlib/main), fully
separate from the Telethon session tree telegram-mcp owns.

Requires the optional tdlib extra: pip install -e ".[tdlib]"
"""

import argparse
import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv

from telegram_mcp.tdlib_download import build_client, raise_if_error

_STATE_TO_REQUIRED_ARG = {
    "authorizationStateWaitPhoneNumber": "phone",
    "authorizationStateWaitCode": "code",
    "authorizationStateWaitPassword": "password",
}


def required_arg_for_state(state: str) -> str | None:
    return _STATE_TO_REQUIRED_ARG.get(state)


async def wait_for_stable_state(client) -> str:
    for _ in range(20):
        state = client.authorization_state
        if state and state != "authorizationStateWaitTdlibParameters":
            return state
        await asyncio.sleep(0.5)
    return client.authorization_state


async def main(phone: str | None, code: str | None, password: str | None) -> None:
    load_dotenv(Path.home() / ".telegram-mcp" / "launchd.env")
    api_id = int(os.environ["TELEGRAM_API_ID"])
    api_hash = os.environ["TELEGRAM_API_HASH"]
    session_dir = Path(
        os.environ.get("TELEGRAM_TDLIB_SESSION_DIR", "~/.telegram-mcp-tdlib/main")
    ).expanduser()

    client = build_client(api_id=api_id, api_hash=api_hash, files_directory=str(session_dir))
    await client.start(wait_login=False)

    state = await wait_for_stable_state(client)
    print(f"Current authorization state: {state}")

    required_arg = required_arg_for_state(state)
    supplied = {"phone": phone, "code": code, "password": password}.get(required_arg)

    if required_arg and not supplied:
        print(
            f"Need --{required_arg}. Re-run: "
            f"PYTHONPATH=src .venv/bin/python scripts/tdlib_login.py --{required_arg} <value>"
        )
        await client.stop()
        return

    if state == "authorizationStateWaitPhoneNumber":
        raise_if_error(await client.setAuthenticationPhoneNumber(phone_number=phone))
        print("Code requested. Check Telegram on your other devices, then run with --code.")
    elif state == "authorizationStateWaitCode":
        raise_if_error(await client.checkAuthenticationCode(code=code))
        print("Code accepted.")
    elif state == "authorizationStateWaitPassword":
        raise_if_error(await client.checkAuthenticationPassword(password=password))
        print("Password accepted.")
    elif state == "authorizationStateReady":
        me = raise_if_error(await client.getMe())
        print(f"Already logged in: {me}")

    await asyncio.sleep(1)
    print(f"Authorization state now: {client.authorization_state}")
    await client.stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--phone")
    parser.add_argument("--code")
    parser.add_argument("--password")
    args = parser.parse_args()
    asyncio.run(main(args.phone, args.code, args.password))
```

- [ ] **Step 2: Verify it imports cleanly without pytdbot installed**

Run: `cd mcp && PYTHONPATH=src .venv/bin/python -c "import ast; ast.parse(open('scripts/tdlib_login.py').read())"`
Expected: no output, exit code 0 (this only checks the file parses; it does not execute the pytdbot-requiring `main()`, consistent with the POC's own boundary: "script-only, live login deferred to manual run with operator")

- [ ] **Step 3: Run the full suite to confirm no regressions**

Run: `cd mcp && TELEGRAM_API_ID=1 TELEGRAM_API_HASH=hash PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p 'test_*.py'`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add mcp/scripts/tdlib_login.py
git commit -m "feat: add production TDLib login script for the main account"
```

---

## Task 5: Document the rollout in operator workflows

**Files:**
- Modify: `docs/operator-workflows.md`

**Interfaces:**
- Consumes: nothing (docs only).
- Produces: nothing consumed by other tasks — this is the last task.

- [ ] **Step 1: Add a new section**

Append this section to `docs/operator-workflows.md` (after the existing content, as a new `##` section):

```markdown
## TDLib Large-Media Downloads (main account only)

`tg download` (and `download_post()` under it) can optionally route large
media downloads on the `main` account through TDLib instead of Telethon,
based on a measured advantage confirmed in a live POC (+78.7% faster average
elapsed, resumability confirmed on 3 real files — see
`mcp/docs/superpowers/specs/2026-07-01-tdlib-large-media-download-design.md`).
This does **not** change any other Telegram operation or account: reads,
search, sends, and MCP tool downloads (`download_media_batch`,
`download_dialog_media`) stay on Telethon unchanged.

The capability stays off until explicitly enabled. Rollout:

1. Install the optional extra: `pip install -e ".[tdlib]"` (from `mcp/`).
2. Run the one-time interactive login for `main`:
   ```
   PYTHONPATH=src .venv/bin/python scripts/tdlib_login.py --phone +<your number>
   # then, after Telegram sends a code to another active session:
   PYTHONPATH=src .venv/bin/python scripts/tdlib_login.py --code <code>
   # only if 2FA is enabled:
   PYTHONPATH=src .venv/bin/python scripts/tdlib_login.py --password <password>
   ```
3. Set in `main`'s env (`~/.telegram-mcp/launchd.env` or `mcp/.env`):
   ```
   TELEGRAM_TDLIB_ENABLED=true
   ```
   Optional tuning: `TELEGRAM_TDLIB_SESSION_DIR` (default
   `~/.telegram-mcp-tdlib/main`), `TELEGRAM_TDLIB_DOWNLOAD_THRESHOLD_MB`
   (default `20`).
4. Watch telemetry (`download_post_backend` events: `backend`,
   `route_attempted`, `fallback_reason`) for the backend-used distribution
   and fallback rate before considering wider rollout (other accounts, lower
   threshold) — each of those is a separate future decision, not part of
   this change.

Every TDLib failure mode (session not authorized, network error, unsupported
content type, lock not acquired within 5s) falls back to Telethon
automatically using the connection already open for routing — there is no
new failure mode a user can hit from this change.
```

- [ ] **Step 2: Verify the file still renders as valid markdown**

Run: `cd /Users/sereja/Projects/tools/telegram/.claude/worktrees/tdlib-media-download-poc && python3 -c "import pathlib; text = pathlib.Path('docs/operator-workflows.md').read_text(); assert text.count('##') >= 1; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Run the full suite one final time**

Run: `cd mcp && TELEGRAM_API_ID=1 TELEGRAM_API_HASH=hash PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p 'test_*.py'`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add docs/operator-workflows.md
git commit -m "docs: document TDLib main-account rollout in operator workflows"
```

---

## Self-Review Notes

- **Spec coverage:** Architecture routing/fallback → Task 3. Components (`tdlib_download.py`, `download_post.py`, `locking.py`, `tdlib_login.py`) → Tasks 1/2/3/4. Configuration (env vars) → Task 2. Dependencies (optional extra, lazy import) → Task 2 + Global Constraints. Error Handling/Fallback → Task 3 (broad `except Exception`, telemetry `fallback_reason`). Testing boundary (pure logic tested, no live-network unit tests) → Tasks 1/2/3 test design; Task 4 explicitly mirrors the POC's "script-only, manual live run" boundary. Rollout steps → Task 5.
- **Placeholder scan:** no TBD/"add error handling"/"similar to Task N" — every step has literal code or an exact command with expected output.
- **Type consistency:** `should_route_to_tdlib` (Task 2) and its call site (Task 3) use identical keyword names (`account`, `tdlib_enabled`, `content_kind`, `media_size_bytes`, `threshold_mb`). `download_via_tdlib(*, link, session_dir) -> Path` (Task 2) matches its Task 3 call site exactly. `tdlib_download.build_client`/`raise_if_error` (Task 2) match the Task 4 script's imports exactly.
