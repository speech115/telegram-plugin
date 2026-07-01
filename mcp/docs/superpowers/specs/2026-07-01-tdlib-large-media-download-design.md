# TDLib for Large Media Downloads — Design

## Context

[control-plane/docs/adr/2026-06-21-tdlib-is-not-default-runtime.md](../../../control-plane/docs/adr/2026-06-21-tdlib-is-not-default-runtime.md)
forbids TDLib as the default Telegram runtime, but allows an isolated lab
POC gated on a measured advantage over the current `telegram-mcp` (Telethon)
path.

That POC ([experiments/tdlib-media-poc/](../../../experiments/tdlib-media-poc/),
plan at [control-plane/docs/superpowers/plans/2026-07-01-tdlib-media-download-poc.md](../../../control-plane/docs/superpowers/plans/2026-07-01-tdlib-media-download-poc.md))
ran live on 2026-07-01 against 3 real large files (787MB / 454MB / 48MB) on
the `main` account and passed its gate:

| | Telethon | TDLib | |
|---|---|---|---|
| Average elapsed | 298.43s | 63.53s | TDLib +78.7% faster |
| Resumability | not tested | confirmed (`resumed=true` on all 3) | |

Full results: `experiments/tdlib-media-poc/data/RESULTS.md` (not committed —
local live-run artifact per the POC's isolation rules).

This design covers graduating that result into a narrowly-scoped production
capability: **TDLib as an auto-routed backend for large media downloads on
the `main` account only**, everything else stays on Telethon.

## Non-Goals

- TDLib does **not** become a general runtime. Reads, search, sends, and all
  other Telegram operations stay on Telethon, unchanged.
- No other account (`crwddy`, `pl`, `recklessou`, `teamsyncsage`,
  `vermassov`) gets TDLib in this iteration. Each would need its own live
  phone/code(/2FA) login, which is out of scope here.
- No persistent TDLib daemon. Every download gets a fresh, in-process TDLib
  client reconnecting to an already-authorized on-disk session, then tears
  down.
- This does not touch the MCP tool surface (`download_media_batch`,
  `download_dialog_media` in `mcp/src/telegram_mcp/tools/media_tools.py`).
  Those are a separate, general-purpose path bound by the 120s MCP tool
  timeout. TDLib routing applies only to `download_post()` /
  `tg download`, which already exists specifically to bypass that cap for
  large post media.

## Architecture

```
tg download <link> --account main
        │
        ▼
cmd_download() [tg_cli.py]
        │
        ▼
download_post() [download_post.py]  ── Telethon connects, resolves entity+msg (unchanged)
        │
        ├─ account != "main"                              ──► existing Telethon download (unchanged)
        ├─ TELEGRAM_TDLIB_ENABLED != "true"                ──► existing Telethon download (unchanged)
        ├─ media size < TELEGRAM_TDLIB_DOWNLOAD_THRESHOLD_MB ──► existing Telethon download (unchanged)
        ├─ unsupported content type (not video/doc/photo/audio) ──► existing Telethon download (unchanged)
        │
        └─ else: try TDLib (tdlib_download.py), in-process, same asyncio loop
                 │
                 ├─ success ──► copy result into TELEGRAM_DOWNLOAD_DIR, return
                 └─ failure (any) ──► log reason, fall back to the *already-open*
                                      Telethon connection + already-fetched msg
                                      (no second round-trip to resolve the message)
```

The Telethon `client`/`msg` that `download_post()` already fetches to
determine routing doubles as the ready-made fallback path — no extra
Telegram round-trip is spent either deciding to route to TDLib or falling
back from it.

## Components

**`mcp/src/telegram_mcp/tdlib_download.py`** (new) — ports the POC's
proven pieces (`experiments/tdlib-media-poc/benchmark/tdlib_client.py`,
`tdlib_message.py`, and the `raise_if_error`/native-object-access pattern
from `run_tdlib.py`) into the production package:

- `assert_isolated_from_telethon(files_directory: str) -> None` — same
  isolation guard as the POC, marker `.telegram-mcp` (not
  `.telegram-mcp-tdlib`).
- `build_client(...) -> pytdbot.Client` — constructed with
  `use_file_database=True`, `use_chat_info_database=False`,
  `use_message_database=False` (minimize state beyond what file download
  needs — directly addresses the ADR's original worry about TDLib being "a
  second source of truth for sessions, local state, files, and updates").
- `extract_file_id_from_message(message) -> int` — same as the POC,
  ported verbatim (native pytdbot object access, not `to_dict()`).
- `raise_if_error(result)` — same as the POC.
- `download_via_tdlib(link: str, dest_dir: Path) -> Path` — the new
  orchestration function `download_post()` calls: resolves the link via
  TDLib, downloads (`downloadFile(..., synchronous=True)`), returns the
  path. Raises on any failure — the caller decides to fall back.
- `pytdbot` import is **lazy**, inside this module's functions, guarded by
  `TELEGRAM_TDLIB_ENABLED` — nothing in the rest of the package imports
  `tdlib_download.py` at module load time.

**`mcp/src/telegram_mcp/download_post.py`** (modified) — after resolving
`msg`, add the routing check described above; call
`tdlib_download.download_via_tdlib(...)` inside a `try/except`, copy the
result into `dest_dir` on success, fall through to the existing Telethon
`client.download_media(...)` call on any exception. Add
`_record_tool_telemetry`-style logging of which backend served the
request (the CLI currently has no telemetry call for downloads at all —
this is a gap this change also closes).

**`mcp/src/telegram_mcp/locking.py`** (extended) — reuse the existing
`FileSessionLock` pattern for a new lock file under the TDLib session
directory, so two concurrent large downloads on `main` serialize at the
TDLib layer instead of both opening the same SQLite+binlog database at
once. A download that can't acquire the lock within 5 seconds falls
back to Telethon immediately (same fallback path as any other TDLib
failure) rather than blocking indefinitely.

**`mcp/scripts/tdlib_login.py`** (new) — the POC's
`experiments/tdlib-media-poc/benchmark/login_tdlib.py`, promoted: same
`--phone`/`--code`/`--password` multi-invocation CLI, pointed at the
production TDLib session directory. One-time manual step, documented in
`docs/operator-workflows.md`.

## Configuration

New environment variables (`mcp/.env.example`):

```
# Optional: route large media downloads on the main account through TDLib.
# TELEGRAM_TDLIB_ENABLED=false
# TELEGRAM_TDLIB_SESSION_DIR=~/.telegram-mcp-tdlib/main
# TELEGRAM_TDLIB_DOWNLOAD_THRESHOLD_MB=20
```

`TELEGRAM_TDLIB_ENABLED` defaults to `false` — the capability stays off
until an operator turns it on explicitly, consistent with the ADR's "not
default" stance even after graduation.

`TELEGRAM_API_ID`/`TELEGRAM_API_HASH` are reused as-is from the existing
`mcp/.env` (same my.telegram.org app, already established as safe to share
across sessions in the POC).

## Dependencies

`pytdbot`/`tdjson` become an **optional** extras group in
`mcp/pyproject.toml` (e.g. `telegram-mcp[tdlib]`), not a hard dependency.
Reasoning: CI (`.github/workflows/ci.yml`) runs on `ubuntu-latest`; the
POC only verified `tdjson`'s prebuilt native binary on macOS arm64. Making
the dependency optional plus lazily importing it only inside
`tdlib_download.py` means CI, and any install that never sets
`TELEGRAM_TDLIB_ENABLED=true`, never needs `pytdbot` to be importable at
all.

## Error Handling / Fallback

Every failure mode on the TDLib path falls back to Telethon, using the
connection/message already fetched during routing — never a hard failure
introduced by this change:

- TDLib session not authorized / session directory missing
- Network error, timeout, or any `pytdbot.types.Error` response
- Unsupported message content type (sticker, round video, etc. — same
  `extract_file_id_from_message` ValueError as the POC)
- Lock not acquired within timeout (concurrent large download in progress)

Each fallback is logged via `_record_tool_telemetry` with the reason, so
production data accumulates on how often TDLib actually serves the
request vs. falls back — this is the ongoing signal for whether the
capability keeps earning its place, beyond the one-time POC measurement.

## Testing

- Unit tests (`mcp/tests/`) for the pure logic: routing-decision function
  (size/account/content-type → route to TDLib or not), `raise_if_error`,
  `extract_file_id_from_message` — same TDD approach as the POC, using
  real `pytdbot.types` objects in fixtures (the POC's dict-fixture bug is
  the concrete lesson here: fixtures must match what pytdbot actually
  returns).
- No live-network unit tests for `download_via_tdlib` itself — same
  boundary as the POC: pure decision/parsing logic is tested, live
  TDLib/Telegram calls are verified manually.
- Before enabling in production, re-run the live comparison once against a
  fresh set of large files to confirm the measured advantage holds outside
  the original 3-file sample.

## Rollout

1. Land the code with `TELEGRAM_TDLIB_ENABLED` unset (off).
2. Run `mcp/scripts/tdlib_login.py` once for `main` (interactive, as done
   for the POC).
3. Turn on `TELEGRAM_TDLIB_ENABLED=true` for `main`'s daemon.
4. Watch telemetry for a period (backend-used distribution, fallback
   rate) before considering wider rollout (other accounts, lower
   threshold) — each of those is a separate future decision, not part of
   this change.
