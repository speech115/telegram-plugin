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
