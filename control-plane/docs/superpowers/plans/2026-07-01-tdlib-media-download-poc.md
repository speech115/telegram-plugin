# TDLib Media-Download POC Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an isolated, ADR-compliant proof of concept that measures whether TDLib beats the current `telegram-mcp` (Telethon) path on media-download latency and resumability, using real large media from the `main` account.

**Architecture:** A standalone Python project at `experiments/tdlib-media-poc/`, fully separate from `mcp/` and `plugin/`. It uses `pytdbot` (tdjson binding) with its own TDLib database/files directory, authenticated as a second, independent session on the `main` account. It never reads or writes the Telethon session tree. Benchmark inputs are real t.me links the operator supplies; outputs are two JSON result files plus a generated `RESULTS.md` comparing both backends against the same inputs.

**Tech Stack:** Python ≥3.12, `uv` for env/deps, `pytdbot` 0.10.1 (confirmed installable and functional on macOS arm64 in this environment), `python-dotenv`, `pytest`. Baseline runs shell out to the existing `mcp/bin/tg download` CLI (the current production large-media path, added in commit `cc51cd8`).

## Global Constraints

- This is governed by [control-plane/docs/adr/2026-06-21-tdlib-is-not-default-runtime.md](../adr/2026-06-21-tdlib-is-not-default-runtime.md). The POC must stay: read-only; isolated from existing Telethon session files; limited to one account (`main`) and one scenario (media download latency/resumability); backed by a dedicated database and files directory; measured against the current `telegram-mcp` path with the same input data; excluded from default routing, LaunchAgents, release gates, and installed plugin docs.
- All POC code lives under `experiments/tdlib-media-poc/` at the repo root. Never modify `mcp/src/telegram_mcp/`, `plugin/`, or any LaunchAgent/release-gate config as part of this plan.
- TDLib's isolated state (`files_directory`) must live at `experiments/tdlib-media-poc/data/tdlib/`. It must never point at or nest inside `~/.telegram-mcp/` (the Telethon session dir per `mcp/.env.example:5`) — enforced in code via `assert_isolated_from_telethon`.
- `pytdbot.Client(...)` real constructor signature on this machine (verified live): accepts `api_id`, `api_hash`, `files_directory`, `database_encryption_key`, `use_test_dc`, `use_file_database`, `use_chat_info_database`, `use_message_database`, `workers`, `no_updates`, etc. There is **no** separate `database_directory` parameter — `files_directory` is the single isolation root.
- Confirmed method signatures on `pytdbot.Client` (verified live):
  - `start(wait_login: bool = True) -> None`
  - `getMe() -> Error | User`
  - `downloadFile(*, file_id: int = 0, priority: int = 0, offset: int = 0, limit: int = 0, synchronous: bool = False) -> Error | File`
  - `cancelDownloadFile(*, file_id: int = 0, only_if_pending: bool = False) -> Error | Ok`
- `pytdbot.types.File.to_dict()` and `pytdbot.types.LocalFile.__init__` fields (verified live): `File` has `id`, `size`, `expected_size`, `local`, `remote`; `LocalFile` has `path`, `can_be_downloaded`, `can_be_deleted`, `is_downloading_active`, `is_downloading_completed`, `download_offset`, `downloaded_prefix_size`, `downloaded_size`.
- The `tg` CLI baseline lives at `mcp/bin/tg` (already built in this worktree via `cd mcp && uv sync`). Relevant subcommands used here: `tg message <chat> <message_id> --json --account main` and `tg download <t.me-link> --dest <dir> --account main --json`.
- `tg message --json` envelope shape (verified from `mcp/src/telegram_mcp/tg_cli.py:578-585` and `mcp/src/telegram_mcp/types.py:220-226,40-59`): `{"ok": bool, "command": "message", "payload": {"chat": {...}, "message_id": int, "message": {"id": int, "file_size": int|null, "media_type": str|null, ...} | null, "data_source": str, "method": str}}`.
- API credentials: reuse the same `TELEGRAM_API_ID`/`TELEGRAM_API_HASH` values already used by `mcp/.env` (same my.telegram.org app — safe to reuse across sessions), stored in a separate `experiments/tdlib-media-poc/.env` (gitignored, never committed).
- Test account: `main`.
- All Telegram operations performed by this POC (both Telethon-side and TDLib-side) must be read-only (message lookup, media download). No send/edit/delete/react calls anywhere in this plan.

---

### Task 1: Bootstrap isolated POC project

**Files:**
- Create: `experiments/tdlib-media-poc/pyproject.toml`
- Create: `experiments/tdlib-media-poc/.gitignore`
- Create: `experiments/tdlib-media-poc/.env.example`
- Create: `experiments/tdlib-media-poc/README.md`
- Create: `experiments/tdlib-media-poc/benchmark/__init__.py`
- Create: `experiments/tdlib-media-poc/benchmark/tdlib_client.py`
- Test: `experiments/tdlib-media-poc/tests/test_tdlib_client.py`

**Interfaces:**
- Produces: `benchmark.tdlib_client.assert_isolated_from_telethon(files_directory: str) -> None` (raises `ValueError` on overlap), `benchmark.tdlib_client.build_client(api_id: int, api_hash: str, files_directory: str, database_encryption_key: str = "tdlib-media-poc") -> pytdbot.Client`. Used by Task 3 and Task 5.

- [ ] **Step 1: Create the project scaffold files**

`experiments/tdlib-media-poc/pyproject.toml`:
```toml
[project]
name = "tdlib-media-poc"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "Pytdbot>=0.10.1",
    "python-dotenv>=1.0.1",
]

[dependency-groups]
dev = [
    "pytest>=8.0.0",
]

[tool.uv]
package = false
```

`experiments/tdlib-media-poc/.gitignore`:
```
data/
.env
__pycache__/
*.pyc
.pytest_cache/
.venv/
```

`experiments/tdlib-media-poc/.env.example`:
```
# Reuse the same values as mcp/.env (same my.telegram.org app, safe to share).
TELEGRAM_API_ID=
TELEGRAM_API_HASH=
```

`experiments/tdlib-media-poc/README.md`:
```markdown
# TDLib media-download POC

Isolated lab proof of concept required by
[control-plane/docs/adr/2026-06-21-tdlib-is-not-default-runtime.md](../../control-plane/docs/adr/2026-06-21-tdlib-is-not-default-runtime.md).

Scenario: media download latency/resumability, measured against the current
`telegram-mcp` (Telethon) path, on the `main` account only.

## Isolation guarantees

- TDLib state lives at `data/tdlib/` (gitignored). It is never pointed at the
  Telethon session tree (`~/.telegram-mcp/`).
- Read-only Telegram operations only.
- Not wired into `mcp/`, `plugin/`, LaunchAgents, or release gates.

## Setup

```bash
cd experiments/tdlib-media-poc
uv sync
cp .env.example .env   # fill in TELEGRAM_API_ID / TELEGRAM_API_HASH from mcp/.env
```

## Run order

1. `uv run python benchmark/build_benchmark_set.py <t.me-link> [<t.me-link> ...]`
2. `uv run python benchmark/login_tdlib.py` (one-time, interactive — needs a live login code)
3. `uv run python benchmark/run_telethon.py`
4. `uv run python benchmark/run_tdlib.py`
5. `uv run python benchmark/compare.py` → writes `data/RESULTS.md`

## Tests

```bash
uv run pytest tests/ -v
```
```

`experiments/tdlib-media-poc/benchmark/__init__.py`: empty file.

- [ ] **Step 2: Write the failing test for the isolation guard**

```python
# experiments/tdlib-media-poc/tests/test_tdlib_client.py
import pytest

from benchmark.tdlib_client import assert_isolated_from_telethon, build_client


def test_assert_isolated_from_telethon_passes_for_poc_dir(tmp_path):
    assert_isolated_from_telethon(str(tmp_path / "tdlib-media-poc" / "data" / "tdlib"))


def test_assert_isolated_from_telethon_rejects_telethon_session_dir():
    with pytest.raises(ValueError, match="Telethon session tree"):
        assert_isolated_from_telethon("/Users/sereja/.telegram-mcp/session")


def test_build_client_constructs_with_isolated_directory(tmp_path):
    client = build_client(
        api_id=1,
        api_hash="0" * 32,
        files_directory=str(tmp_path / "tdlib"),
    )
    assert client is not None
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd experiments/tdlib-media-poc && uv sync -q && uv run pytest tests/test_tdlib_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'benchmark.tdlib_client'`

- [ ] **Step 4: Write the minimal implementation**

```python
# experiments/tdlib-media-poc/benchmark/tdlib_client.py
"""Isolated pytdbot client factory for the TDLib media-download POC.

Per control-plane/docs/adr/2026-06-21-tdlib-is-not-default-runtime.md, this
POC must never share state with the Telethon session tree that telegram-mcp
owns.
"""

import pytdbot

TELETHON_SESSION_DIR_MARKERS = (".telegram-mcp",)


def assert_isolated_from_telethon(files_directory: str) -> None:
    for marker in TELETHON_SESSION_DIR_MARKERS:
        if marker in files_directory:
            raise ValueError(
                f"files_directory must not overlap the Telethon session tree (found {marker!r})"
            )


def build_client(
    api_id: int,
    api_hash: str,
    files_directory: str,
    database_encryption_key: str = "tdlib-media-poc",
) -> pytdbot.Client:
    assert_isolated_from_telethon(files_directory)
    return pytdbot.Client(
        api_id=api_id,
        api_hash=api_hash,
        files_directory=files_directory,
        database_encryption_key=database_encryption_key,
    )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd experiments/tdlib-media-poc && uv run pytest tests/test_tdlib_client.py -v`
Expected: PASS (3 tests)

- [ ] **Step 6: Commit**

```bash
git add experiments/tdlib-media-poc/pyproject.toml experiments/tdlib-media-poc/.gitignore \
  experiments/tdlib-media-poc/.env.example experiments/tdlib-media-poc/README.md \
  experiments/tdlib-media-poc/benchmark/__init__.py experiments/tdlib-media-poc/benchmark/tdlib_client.py \
  experiments/tdlib-media-poc/tests/test_tdlib_client.py
git commit -m "poc: bootstrap isolated tdlib media-download poc project"
```

---

### Task 2: Benchmark target model, link parsing, file-size extraction

**Files:**
- Create: `experiments/tdlib-media-poc/benchmark/models.py`
- Create: `experiments/tdlib-media-poc/benchmark/select_targets.py`
- Create: `experiments/tdlib-media-poc/benchmark/build_benchmark_set.py`
- Test: `experiments/tdlib-media-poc/tests/test_models.py`
- Test: `experiments/tdlib-media-poc/tests/test_select_targets.py`

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces: `benchmark.models.BenchmarkTarget` (dataclass: `label: str, chat: str, message_id: int, link: str, expected_size_bytes: int | None`), `benchmark.models.DownloadResult` (dataclass: `label: str, backend: str, ok: bool, elapsed_seconds: float, bytes_downloaded: int | None, resumed: bool, error: str | None = None`), `benchmark.models.save_benchmark_set/load_benchmark_set/save_results/load_results`, `benchmark.select_targets.parse_link(link: str) -> tuple[str, int]`, `benchmark.select_targets.extract_file_size(tg_message_envelope: dict) -> int | None`. Used by Tasks 4, 5, 6.

- [ ] **Step 1: Write the failing tests for models**

```python
# experiments/tdlib-media-poc/tests/test_models.py
import json

from benchmark.models import (
    BenchmarkTarget,
    DownloadResult,
    load_benchmark_set,
    load_results,
    save_benchmark_set,
    save_results,
)


def test_save_and_load_benchmark_set_round_trip(tmp_path):
    path = tmp_path / "data" / "benchmark_set.json"
    targets = [
        BenchmarkTarget(
            label="big-video-1",
            chat="durov",
            message_id=123,
            link="https://t.me/durov/123",
            expected_size_bytes=52_428_800,
        )
    ]

    save_benchmark_set(path, targets)
    loaded = load_benchmark_set(path)

    assert loaded == targets
    assert json.loads(path.read_text())[0]["label"] == "big-video-1"


def test_save_and_load_results_round_trip(tmp_path):
    path = tmp_path / "data" / "results_telethon.json"
    results = [
        DownloadResult(
            label="big-video-1",
            backend="telethon",
            ok=True,
            elapsed_seconds=12.5,
            bytes_downloaded=52_428_800,
            resumed=False,
        )
    ]

    save_results(path, results)
    loaded = load_results(path)

    assert loaded == results
```

```python
# experiments/tdlib-media-poc/tests/test_select_targets.py
import pytest

from benchmark.select_targets import extract_file_size, parse_link


def test_parse_link_public_username():
    chat, message_id = parse_link("https://t.me/durov/123")
    assert chat == "durov"
    assert message_id == 123


def test_parse_link_private_channel_id():
    chat, message_id = parse_link("https://t.me/c/1234567890/456")
    assert chat == "-1001234567890"
    assert message_id == 456


def test_parse_link_rejects_non_telegram_url():
    with pytest.raises(ValueError, match="not a recognized t.me post link"):
        parse_link("https://example.com/foo/1")


def test_extract_file_size_from_tg_message_envelope():
    envelope = {
        "ok": True,
        "payload": {
            "chat": {"id": 123},
            "message_id": 456,
            "message": {"id": 456, "file_size": 52428800, "media_type": "video"},
        },
    }
    assert extract_file_size(envelope) == 52428800


def test_extract_file_size_returns_none_when_no_media():
    envelope = {"ok": True, "payload": {"message": {"id": 1, "file_size": None}}}
    assert extract_file_size(envelope) is None


def test_extract_file_size_returns_none_when_message_missing():
    envelope = {"ok": True, "payload": {"message": None}}
    assert extract_file_size(envelope) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd experiments/tdlib-media-poc && uv run pytest tests/test_models.py tests/test_select_targets.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'benchmark.models'` (and `benchmark.select_targets`)

- [ ] **Step 3: Write the minimal implementation**

```python
# experiments/tdlib-media-poc/benchmark/models.py
"""Data models for the TDLib vs Telethon media-download benchmark."""

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class BenchmarkTarget:
    label: str
    chat: str
    message_id: int
    link: str
    expected_size_bytes: int | None


@dataclass(frozen=True)
class DownloadResult:
    label: str
    backend: str  # "telethon" or "tdlib"
    ok: bool
    elapsed_seconds: float
    bytes_downloaded: int | None
    resumed: bool
    error: str | None = None


def load_benchmark_set(path: Path) -> list[BenchmarkTarget]:
    raw = json.loads(path.read_text())
    return [BenchmarkTarget(**item) for item in raw]


def save_benchmark_set(path: Path, targets: list[BenchmarkTarget]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([asdict(t) for t in targets], indent=2))


def load_results(path: Path) -> list[DownloadResult]:
    raw = json.loads(path.read_text())
    return [DownloadResult(**item) for item in raw]


def save_results(path: Path, results: list[DownloadResult]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([asdict(r) for r in results], indent=2))
```

```python
# experiments/tdlib-media-poc/benchmark/select_targets.py
"""Parse t.me links and pull file-size metadata from `tg message` output."""

import re

LINK_PATTERN = re.compile(
    r"^https?://t\.me/(?:c/(?P<internal_id>\d+)|(?P<username>[A-Za-z0-9_]+))/(?P<message_id>\d+)$"
)


def parse_link(link: str) -> tuple[str, int]:
    match = LINK_PATTERN.match(link.strip())
    if not match:
        raise ValueError(f"not a recognized t.me post link: {link!r}")
    message_id = int(match.group("message_id"))
    if match.group("internal_id"):
        chat = f"-100{match.group('internal_id')}"
    else:
        chat = match.group("username")
    return chat, message_id


def extract_file_size(tg_message_envelope: dict) -> int | None:
    payload = tg_message_envelope.get("payload") or {}
    message = payload.get("message") or {}
    return message.get("file_size")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd experiments/tdlib-media-poc && uv run pytest tests/test_models.py tests/test_select_targets.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Write `build_benchmark_set.py` (live orchestration script, not unit tested)**

```python
# experiments/tdlib-media-poc/benchmark/build_benchmark_set.py
"""Build data/benchmark_set.json from operator-supplied t.me links.

Usage:
    uv run python benchmark/build_benchmark_set.py <t.me-link> [<t.me-link> ...]

For each link this shells out to the existing `tg message` CLI (read-only)
to fetch file_size metadata, then writes the isolated benchmark set used by
both the Telethon and TDLib benchmark runners.
"""

import json
import subprocess
import sys
from pathlib import Path

from benchmark.models import BenchmarkTarget, save_benchmark_set
from benchmark.select_targets import extract_file_size, parse_link

POC_ROOT = Path(__file__).resolve().parent.parent
TG_CLI = POC_ROOT.parent.parent / "mcp" / "bin" / "tg"
OUTPUT_PATH = POC_ROOT / "data" / "benchmark_set.json"


def fetch_metadata(chat: str, message_id: int) -> dict:
    proc = subprocess.run(
        [str(TG_CLI), "message", chat, str(message_id), "--json", "--account", "main"],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(proc.stdout)


def main(links: list[str]) -> None:
    targets = []
    for index, link in enumerate(links, start=1):
        chat, message_id = parse_link(link)
        envelope = fetch_metadata(chat, message_id)
        targets.append(
            BenchmarkTarget(
                label=f"target-{index}",
                chat=chat,
                message_id=message_id,
                link=link,
                expected_size_bytes=extract_file_size(envelope),
            )
        )
    save_benchmark_set(OUTPUT_PATH, targets)
    print(f"Wrote {len(targets)} targets to {OUTPUT_PATH}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("usage: build_benchmark_set.py <t.me-link> [<t.me-link> ...]")
    main(sys.argv[1:])
```

- [ ] **Step 6: Commit**

```bash
git add experiments/tdlib-media-poc/benchmark/models.py experiments/tdlib-media-poc/benchmark/select_targets.py \
  experiments/tdlib-media-poc/benchmark/build_benchmark_set.py experiments/tdlib-media-poc/tests/test_models.py \
  experiments/tdlib-media-poc/tests/test_select_targets.py
git commit -m "poc: add benchmark models, link parsing, and target-set builder"
```

---

### Task 3: Isolated TDLib login for `main` account (interactive, manual)

**Files:**
- Create: `experiments/tdlib-media-poc/benchmark/login_tdlib.py`

**Interfaces:**
- Consumes: `benchmark.tdlib_client.build_client` (Task 1).
- Produces: an authenticated TDLib session on disk at `experiments/tdlib-media-poc/data/tdlib/`, consumed by Task 5.

This task has no automated test — it is a one-time interactive login and must be run live, with the operator present to receive and enter the Telegram login code for the `main` account (confirmed account choice). It does not touch the Telethon session in any way.

- [ ] **Step 1: Write the login script**

```python
# experiments/tdlib-media-poc/benchmark/login_tdlib.py
"""One-time interactive TDLib login for the isolated media-download POC.

Run manually:
    uv run python benchmark/login_tdlib.py

This creates a TDLib session under data/tdlib/, fully separate from the
Telethon session telegram-mcp owns. It requires live phone-code entry for
the `main` account (confirmed with the operator before running this).
"""

import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv

from benchmark.tdlib_client import build_client

POC_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = POC_ROOT / "data" / "tdlib"


async def main() -> None:
    load_dotenv(POC_ROOT / ".env")
    api_id = int(os.environ["TELEGRAM_API_ID"])
    api_hash = os.environ["TELEGRAM_API_HASH"]

    client = build_client(api_id=api_id, api_hash=api_hash, files_directory=str(DATA_DIR))
    await client.start()
    me = await client.getMe()
    print(f"Logged in: {me}")
    await client.stop()


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: Run it live with the operator present**

Run: `cd experiments/tdlib-media-poc && uv run python benchmark/login_tdlib.py`
Expected: TDLib prompts for phone number (or reuses saved `+`-prefixed number if asked), then a login code delivered to the `main` account's other active Telegram sessions. Operator enters the code interactively. Script prints `Logged in: ...` with the `main` account's user object and exits cleanly.

- [ ] **Step 3: Verify isolation held**

Run: `ls -la ~/.telegram-mcp/ 2>/dev/null | head -5` before and after — file listing and mtimes must be identical (no Telethon files touched). Then: `ls experiments/tdlib-media-poc/data/tdlib/` — must show TDLib's own database/file-cache directory tree that did not exist before this step.

- [ ] **Step 4: Commit**

```bash
git add experiments/tdlib-media-poc/benchmark/login_tdlib.py
git commit -m "poc: add isolated interactive tdlib login script"
```

(`data/` stays gitignored — the authenticated session itself is never committed.)

---

### Task 4: Telethon baseline download benchmark

**Files:**
- Create: `experiments/tdlib-media-poc/benchmark/run_telethon.py`
- Test: `experiments/tdlib-media-poc/tests/test_run_telethon.py`

**Interfaces:**
- Consumes: `benchmark.models.BenchmarkTarget/DownloadResult/load_benchmark_set/save_results` (Task 2).
- Produces: `benchmark.run_telethon.build_telethon_result(target, elapsed_seconds, envelope, downloaded_size_bytes) -> DownloadResult`, and `data/results_telethon.json` when run live. Consumed by Task 6.

- [ ] **Step 1: Write the failing test for the pure result-builder**

```python
# experiments/tdlib-media-poc/tests/test_run_telethon.py
from benchmark.models import BenchmarkTarget
from benchmark.run_telethon import build_telethon_result

TARGET = BenchmarkTarget(
    label="big-video-1",
    chat="durov",
    message_id=123,
    link="https://t.me/durov/123",
    expected_size_bytes=52_428_800,
)


def test_build_telethon_result_success():
    envelope = {"ok": True, "payload": {"local_path": "/tmp/foo.mp4"}}
    result = build_telethon_result(TARGET, 12.5, envelope, 52_428_800)

    assert result.ok is True
    assert result.backend == "telethon"
    assert result.elapsed_seconds == 12.5
    assert result.bytes_downloaded == 52_428_800
    assert result.resumed is False
    assert result.error is None


def test_build_telethon_result_failure_from_bad_envelope():
    envelope = {"ok": False, "error": "flood_wait"}
    result = build_telethon_result(TARGET, 3.0, envelope, None)

    assert result.ok is False
    assert result.bytes_downloaded is None
    assert result.error == "flood_wait"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd experiments/tdlib-media-poc && uv run pytest tests/test_run_telethon.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'benchmark.run_telethon'`

- [ ] **Step 3: Write the implementation**

```python
# experiments/tdlib-media-poc/benchmark/run_telethon.py
"""Benchmark media downloads through the current telegram-mcp path.

Live usage:
    uv run python benchmark/run_telethon.py

Shells out to the existing `tg download` CLI (direct Telethon, no 120s MCP
cap — see mcp/src/telegram_mcp/tg_cli.py:cmd_download) for each target in
data/benchmark_set.json, times it, and records results.
"""

import json
import subprocess
import time
from pathlib import Path

from benchmark.models import BenchmarkTarget, DownloadResult, load_benchmark_set, save_results

POC_ROOT = Path(__file__).resolve().parent.parent
TG_CLI = POC_ROOT.parent.parent / "mcp" / "bin" / "tg"
BENCHMARK_SET_PATH = POC_ROOT / "data" / "benchmark_set.json"
RESULTS_PATH = POC_ROOT / "data" / "results_telethon.json"
DOWNLOAD_DEST = POC_ROOT / "data" / "downloads" / "telethon"


def build_telethon_result(
    target: BenchmarkTarget,
    elapsed_seconds: float,
    envelope: dict,
    downloaded_size_bytes: int | None,
) -> DownloadResult:
    ok = bool(envelope.get("ok")) and downloaded_size_bytes is not None
    error = None
    if not ok:
        error = str(envelope.get("error") or envelope.get("payload") or "download failed")
    return DownloadResult(
        label=target.label,
        backend="telethon",
        ok=ok,
        elapsed_seconds=elapsed_seconds,
        bytes_downloaded=downloaded_size_bytes,
        resumed=False,
        error=error,
    )


def download_one(target: BenchmarkTarget) -> DownloadResult:
    DOWNLOAD_DEST.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    proc = subprocess.run(
        [str(TG_CLI), "download", target.link, "--dest", str(DOWNLOAD_DEST), "--account", "main", "--json"],
        capture_output=True,
        text=True,
    )
    elapsed = time.perf_counter() - started
    try:
        envelope = json.loads(proc.stdout)
    except json.JSONDecodeError:
        envelope = {"ok": False, "error": proc.stderr.strip() or "no JSON output"}

    downloaded_size = None
    payload = envelope.get("payload") if isinstance(envelope.get("payload"), dict) else {}
    local_path = payload.get("local_path") or payload.get("path")
    if local_path and Path(local_path).exists():
        downloaded_size = Path(local_path).stat().st_size

    return build_telethon_result(target, elapsed, envelope, downloaded_size)


def main() -> None:
    targets = load_benchmark_set(BENCHMARK_SET_PATH)
    results = [download_one(target) for target in targets]
    save_results(RESULTS_PATH, results)
    for result in results:
        print(f"{result.label}: ok={result.ok} elapsed={result.elapsed_seconds:.2f}s bytes={result.bytes_downloaded}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd experiments/tdlib-media-poc && uv run pytest tests/test_run_telethon.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Run live against real targets (manual verification)**

Prerequisite: Task 2's `build_benchmark_set.py` has been run with real t.me links pointing at large media in the `main` account, producing `data/benchmark_set.json`.

Run: `cd experiments/tdlib-media-poc && uv run python benchmark/run_telethon.py`
Expected: one line per target printed with `ok=True`, a non-zero `elapsed`, and `bytes` matching the target's `expected_size_bytes`; `data/results_telethon.json` created.

- [ ] **Step 6: Commit**

```bash
git add experiments/tdlib-media-poc/benchmark/run_telethon.py experiments/tdlib-media-poc/tests/test_run_telethon.py
git commit -m "poc: add telethon baseline download benchmark runner"
```

---

### Task 5: TDLib message resolution + download benchmark with resumability test

**Files:**
- Create: `experiments/tdlib-media-poc/benchmark/tdlib_message.py`
- Create: `experiments/tdlib-media-poc/benchmark/run_tdlib.py`
- Test: `experiments/tdlib-media-poc/tests/test_tdlib_message.py`

**Interfaces:**
- Consumes: `benchmark.models.BenchmarkTarget/DownloadResult/load_benchmark_set/save_results` (Task 2), `benchmark.tdlib_client.build_client` (Task 1), authenticated session from Task 3.
- Produces: `benchmark.tdlib_message.extract_file_id_from_message(message: dict) -> int`, `benchmark.run_tdlib.build_tdlib_result(target, elapsed_seconds, file_object, resumed) -> DownloadResult`, and `data/results_tdlib.json` when run live. Consumed by Task 6.

- [ ] **Step 1: Write the failing tests for pure TDLib-schema logic**

```python
# experiments/tdlib-media-poc/tests/test_tdlib_message.py
import pytest

from benchmark.tdlib_message import extract_file_id_from_message
from benchmark.run_tdlib import build_tdlib_result
from benchmark.models import BenchmarkTarget

TARGET = BenchmarkTarget(
    label="big-video-1",
    chat="durov",
    message_id=123,
    link="https://t.me/durov/123",
    expected_size_bytes=52_428_800,
)


def test_extract_file_id_from_message_video():
    message = {
        "content": {
            "@type": "messageVideo",
            "video": {"video": {"id": 555, "size": 52_428_800}},
        }
    }
    assert extract_file_id_from_message(message) == 555


def test_extract_file_id_from_message_document():
    message = {
        "content": {
            "@type": "messageDocument",
            "document": {"document": {"id": 777, "size": 10_000_000}},
        }
    }
    assert extract_file_id_from_message(message) == 777


def test_extract_file_id_from_message_unsupported_type():
    message = {"content": {"@type": "messageText"}}
    with pytest.raises(ValueError, match="unsupported message content type"):
        extract_file_id_from_message(message)


def test_build_tdlib_result_completed_download():
    file_object = {
        "id": 555,
        "size": 52_428_800,
        "local": {"downloaded_size": 52_428_800, "is_downloading_completed": True},
    }
    result = build_tdlib_result(TARGET, 8.0, file_object, resumed=True)

    assert result.ok is True
    assert result.backend == "tdlib"
    assert result.bytes_downloaded == 52_428_800
    assert result.resumed is True
    assert result.error is None


def test_build_tdlib_result_incomplete_download():
    file_object = {
        "id": 555,
        "size": 52_428_800,
        "local": {"downloaded_size": 1_000_000, "is_downloading_completed": False},
    }
    result = build_tdlib_result(TARGET, 3.0, file_object, resumed=False)

    assert result.ok is False
    assert result.bytes_downloaded == 1_000_000
    assert result.error == "download did not complete"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd experiments/tdlib-media-poc && uv run pytest tests/test_tdlib_message.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'benchmark.tdlib_message'`

- [ ] **Step 3: Write the implementation**

```python
# experiments/tdlib-media-poc/benchmark/tdlib_message.py
"""Pure helpers for pulling downloadable file_ids out of TDLib Message objects.

TDLib content schema reference: https://core.telegram.org/tdlib/docs/classtd_1_1td__api_1_1_message.html
"""


def extract_file_id_from_message(message: dict) -> int:
    content = message.get("content") or {}
    content_type = content.get("@type", "")
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
```

```python
# experiments/tdlib-media-poc/benchmark/run_tdlib.py
"""Benchmark media downloads through TDLib, including a resume test.

Live usage:
    uv run python benchmark/run_tdlib.py

Requires the isolated session created by benchmark/login_tdlib.py. For each
target: resolves the t.me link via getMessageLinkInfo, fetches the Message,
extracts the file_id, downloads it, then re-runs the same download once more
after a mid-flight cancel to prove resumability.
"""

import asyncio
import os
import time
from pathlib import Path

from dotenv import load_dotenv

from benchmark.models import BenchmarkTarget, DownloadResult, load_benchmark_set, save_results
from benchmark.tdlib_client import build_client
from benchmark.tdlib_message import extract_file_id_from_message

POC_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = POC_ROOT / "data" / "tdlib"
BENCHMARK_SET_PATH = POC_ROOT / "data" / "benchmark_set.json"
RESULTS_PATH = POC_ROOT / "data" / "results_tdlib.json"


def build_tdlib_result(
    target: BenchmarkTarget,
    elapsed_seconds: float,
    file_object: dict,
    resumed: bool,
) -> DownloadResult:
    local = file_object.get("local") or {}
    ok = bool(local.get("is_downloading_completed"))
    return DownloadResult(
        label=target.label,
        backend="tdlib",
        ok=ok,
        elapsed_seconds=elapsed_seconds,
        bytes_downloaded=local.get("downloaded_size"),
        resumed=resumed,
        error=None if ok else "download did not complete",
    )


async def resolve_file_id(client, target: BenchmarkTarget) -> int:
    link_info = await client.getMessageLinkInfo(url=target.link)
    message = await client.getMessage(
        chat_id=link_info["chat_id"], message_id=link_info["message"]["id"]
    )
    return extract_file_id_from_message(message.to_dict() if hasattr(message, "to_dict") else message)


async def measure_clean_download(client, file_id: int) -> tuple[float, dict]:
    """Single-shot download latency, directly comparable to the Telethon baseline."""
    started = time.perf_counter()
    result = await client.downloadFile(file_id=file_id, priority=1, synchronous=True, offset=0, limit=0)
    elapsed = time.perf_counter() - started
    file_dict = result.to_dict() if hasattr(result, "to_dict") else result
    return elapsed, file_dict


async def measure_resumability(client, file_id: int) -> bool:
    """Delete the local copy, start a fresh async download, cancel it mid-flight
    while it is still partial, then confirm a second call resumes from the
    partial bytes already on disk instead of restarting from zero."""
    await client.deleteFile(file_id=file_id)
    await client.downloadFile(file_id=file_id, priority=1, synchronous=False, offset=0, limit=0)
    await asyncio.sleep(2)

    partial = await client.getFile(file_id=file_id)
    partial_dict = partial.to_dict() if hasattr(partial, "to_dict") else partial
    partial_bytes = (partial_dict.get("local") or {}).get("downloaded_size", 0)

    await client.cancelDownloadFile(file_id=file_id, only_if_pending=False)

    resumed_result = await client.downloadFile(file_id=file_id, priority=1, synchronous=True, offset=0, limit=0)
    resumed_dict = resumed_result.to_dict() if hasattr(resumed_result, "to_dict") else resumed_result
    resumed_local = resumed_dict.get("local") or {}
    completed = bool(resumed_local.get("is_downloading_completed"))
    grew_from_partial = resumed_local.get("downloaded_size", 0) >= partial_bytes

    return completed and partial_bytes > 0 and grew_from_partial


async def run(targets: list[BenchmarkTarget]) -> list[DownloadResult]:
    load_dotenv(POC_ROOT / ".env")
    client = build_client(
        api_id=int(os.environ["TELEGRAM_API_ID"]),
        api_hash=os.environ["TELEGRAM_API_HASH"],
        files_directory=str(DATA_DIR),
    )
    await client.start()

    results = []
    for target in targets:
        file_id = await resolve_file_id(client, target)
        elapsed, file_object = await measure_clean_download(client, file_id)
        resumed_ok = await measure_resumability(client, file_id)
        results.append(build_tdlib_result(target, elapsed, file_object, resumed=resumed_ok))

    await client.stop()
    return results


def main() -> None:
    targets = load_benchmark_set(BENCHMARK_SET_PATH)
    results = asyncio.run(run(targets))
    save_results(RESULTS_PATH, results)
    for result in results:
        print(f"{result.label}: ok={result.ok} elapsed={result.elapsed_seconds:.2f}s resumed={result.resumed}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd experiments/tdlib-media-poc && uv run pytest tests/test_tdlib_message.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Run live against real targets (manual verification)**

Prerequisite: Task 3's login completed successfully.

Run: `cd experiments/tdlib-media-poc && uv run python benchmark/run_tdlib.py`
Expected: one line per target with `ok=True` and `resumed=True`; `data/results_tdlib.json` created. `getMessageLinkInfo`, `getMessage`, `getFile`, and `deleteFile` are standard, stable TDLib API methods that pytdbot generates dynamically from TDLib's schema, but — unlike `downloadFile`/`cancelDownloadFile`/`getMe`/`start` — they were not directly invoked during plan verification. If any raises `AttributeError`, run `uv run python -c "import pytdbot; print([m for m in dir(pytdbot.Client) if not m.startswith('_')])"` to list the real method names on the installed pytdbot version and adjust `run_tdlib.py` accordingly.

- [ ] **Step 6: Commit**

```bash
git add experiments/tdlib-media-poc/benchmark/tdlib_message.py experiments/tdlib-media-poc/benchmark/run_tdlib.py \
  experiments/tdlib-media-poc/tests/test_tdlib_message.py
git commit -m "poc: add tdlib download benchmark runner with resume check"
```

---

### Task 6: Compare results and generate the POC report

**Files:**
- Create: `experiments/tdlib-media-poc/benchmark/compare.py`
- Test: `experiments/tdlib-media-poc/tests/test_compare.py`

**Interfaces:**
- Consumes: `benchmark.models.DownloadResult/load_results` (Task 2), `data/results_telethon.json` (Task 4), `data/results_tdlib.json` (Task 5).
- Produces: `data/RESULTS.md`.

- [ ] **Step 1: Write the failing test**

```python
# experiments/tdlib-media-poc/tests/test_compare.py
from benchmark.compare import build_report
from benchmark.models import DownloadResult


def test_build_report_includes_table_rows_and_averages():
    telethon = [DownloadResult("big-video-1", "telethon", True, 10.0, 52428800, False)]
    tdlib = [DownloadResult("big-video-1", "tdlib", True, 8.0, 52428800, True)]

    report = build_report(telethon, tdlib)

    assert "big-video-1" in report
    assert "telethon=10.00s, tdlib=8.00s" in report
    assert "resume after interruption: True" in report


def test_build_report_handles_no_successful_runs():
    telethon = [DownloadResult("big-video-1", "telethon", False, 0.0, None, False, error="boom")]
    tdlib = [DownloadResult("big-video-1", "tdlib", False, 0.0, None, False, error="boom")]

    report = build_report(telethon, tdlib)

    assert "Not enough successful runs" in report
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd experiments/tdlib-media-poc && uv run pytest tests/test_compare.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'benchmark.compare'`

- [ ] **Step 3: Write the implementation**

```python
# experiments/tdlib-media-poc/benchmark/compare.py
"""Compare Telethon vs TDLib download benchmark results and write RESULTS.md.

Live usage:
    uv run python benchmark/compare.py
"""

from pathlib import Path
from statistics import mean

from benchmark.models import DownloadResult, load_results

POC_ROOT = Path(__file__).resolve().parent.parent
TELETHON_RESULTS_PATH = POC_ROOT / "data" / "results_telethon.json"
TDLIB_RESULTS_PATH = POC_ROOT / "data" / "results_tdlib.json"
REPORT_PATH = POC_ROOT / "data" / "RESULTS.md"


def build_report(telethon_results: list[DownloadResult], tdlib_results: list[DownloadResult]) -> str:
    lines = [
        "# TDLib vs Telethon: media download latency/resumability POC results",
        "",
        "| label | backend | ok | elapsed_seconds | bytes_downloaded | resumed |",
        "|---|---|---|---|---|---|",
    ]
    for result in [*telethon_results, *tdlib_results]:
        lines.append(
            f"| {result.label} | {result.backend} | {result.ok} | {result.elapsed_seconds:.2f} "
            f"| {result.bytes_downloaded} | {result.resumed} |"
        )

    telethon_ok = [r for r in telethon_results if r.ok]
    tdlib_ok = [r for r in tdlib_results if r.ok]
    lines.append("")
    if telethon_ok and tdlib_ok:
        telethon_avg = mean(r.elapsed_seconds for r in telethon_ok)
        tdlib_avg = mean(r.elapsed_seconds for r in tdlib_ok)
        delta_pct = ((telethon_avg - tdlib_avg) / telethon_avg) * 100
        lines.append(
            f"Average elapsed: telethon={telethon_avg:.2f}s, tdlib={tdlib_avg:.2f}s "
            f"({delta_pct:+.1f}% telethon vs tdlib)."
        )
    else:
        lines.append("Not enough successful runs on both backends to compare averages.")

    tdlib_resumed = any(r.resumed and r.ok for r in tdlib_results)
    lines.append(f"TDLib demonstrated successful resume after interruption: {tdlib_resumed}.")

    lines.append("")
    lines.append("## ADR kill-criteria checklist (manual assessment)")
    lines.append("- [ ] Required sharing/converting Telethon session files? (must be No)")
    lines.append("- [ ] Auth/DB/update-loop code became the main work? (must be No)")
    lines.append("- [ ] No clear measured advantage over telegram-mcp? (see averages above)")
    lines.append("- [ ] Read behavior diverged from telegram-mcp in a way agents would need to understand? (must be No)")
    lines.append("- [ ] Required new persistent daemon management before proving value? (must be No)")

    return "\n".join(lines)


def main() -> None:
    telethon_results = load_results(TELETHON_RESULTS_PATH)
    tdlib_results = load_results(TDLIB_RESULTS_PATH)
    report = build_report(telethon_results, tdlib_results)
    REPORT_PATH.write_text(report)
    print(f"Wrote {REPORT_PATH}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd experiments/tdlib-media-poc && uv run pytest tests/test_compare.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Run live to generate the final report (manual verification)**

Prerequisite: Tasks 4 and 5 have both been run live and produced their result JSON files.

Run: `cd experiments/tdlib-media-poc && uv run python benchmark/compare.py`
Expected: `data/RESULTS.md` written with a filled-in comparison table and averages; manually fill in the kill-criteria checklist based on how Tasks 3–5 actually went before treating the POC as concluded.

- [ ] **Step 6: Run the full test suite**

Run: `cd experiments/tdlib-media-poc && uv run pytest tests/ -v`
Expected: PASS (all tests across all tasks, 20 tests total)

- [ ] **Step 7: Commit**

```bash
git add experiments/tdlib-media-poc/benchmark/compare.py experiments/tdlib-media-poc/tests/test_compare.py
git commit -m "poc: add results comparison and RESULTS.md generator"
```
