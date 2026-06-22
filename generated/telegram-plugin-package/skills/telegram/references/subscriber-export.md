# Subscriber Export

Use this for all subscribers/members of a channel or group.

## Default Command

```bash
python3 skills/telegram/scripts/run_export_channel_subscribers.py @channel_username --progress --resume
```

Fallback only when the plugin bundle is unavailable:

```bash
python3 "$HOME/.agents/skills/telegram/scripts/run_export_channel_subscribers.py" @channel_username --progress --resume
```

The wrapper resolves the canonical exporter path, prefers the plugin source when
available, falls back to the live standalone tree, and refuses to run if the
selected exporter script is missing.

Do not use `get_participants` as the final result for subscriber export requests. Use it only if the exporter is unavailable and say clearly that the result is incomplete/probe-only. A result around `200` is a Telegram API slice cap, not the full member list.

## Output

Default artifacts:

- `${TELEGRAM_SUBSCRIBER_RUNTIME_DIR:-$HOME/.cache/telegram-subscriber-export}/artifacts/YYYY-MM-DD-<channel>-subscribers.md`
- `${TELEGRAM_SUBSCRIBER_RUNTIME_DIR:-$HOME/.cache/telegram-subscriber-export}/artifacts/YYYY-MM-DD-<channel>-subscribers.json`

Use the default output path unless the user gives another destination. For
workspace writeback, pass an explicit `--out-dir`, for example
`<repo>/outputs/telegram`.

Runtime-only state is separate from deliverable artifacts:

- session copy and resume checkpoint live under `${TELEGRAM_SUBSCRIBER_RUNTIME_DIR:-$HOME/.cache/telegram-subscriber-export}` by default;
- runtime directory permissions are forced to owner-only (`0700`);
- override with `--runtime-dir` when a different runtime path is needed;
- do not bundle or publish `.session`, checkpoint, or runtime directories with subscriber outputs.

Expected result fields:

- `visible_count`: Telegram's channel counter.
- `exported_count`: unique users actually returned by Telegram API.
- `missing`: `visible_count - exported_count` when the counter is known.
- `completeness`: `exact`, `api_visible_gap`, or `unknown`.
- `md` / `json`: artifact paths.

Do not include Telethon `access_hash` values in normal artifacts. The exporter
omits them by default; use `--include-access-hash` only for an explicit debug
or protocol-level audit need, and treat that output as sensitive.

If `exported_count < visible_count`, say so plainly. Usually this means Telegram keeps one or more deleted, hidden, or non-indexed accounts in the counter but does not expose those users through participant APIs. Do not claim exact completeness unless the counts match.

## Exporter Behavior

- The exporter uses local `telegram-mirror` Telethon credentials and copies the seed `.session` into the runtime directory before connecting to avoid shared-session `database is locked` errors.
- It first pulls cheap recent/admin/bot slices.
- It then runs single-character latin/digit/cyrillic search slices.
- If a slice hits Telegram's page cap, it adaptively splits only that capped slice one character deeper.
- In the default fast path, capped-slice splitting stops once the remaining gap
  to Telegram's visible counter is within `--accept-counter-gap` (default `5`).
  This avoids spending minutes chasing a few counter-only or hidden accounts.
- It writes a hidden checkpoint in the runtime directory; `--resume` continues after interruption or flood-wait pain.
- Default `--profile fast` and `--max-depth 1` are the normal stable path.

## Audit Mode

When the user challenges completeness or asks for proof:

```bash
python3 skills/telegram/scripts/run_export_channel_subscribers.py @channel_username --profile exhaustive --progress --resume --accept-counter-gap 0 --max-depth 1
```

Treat `exhaustive` as a confidence check, not the default. Use
`--accept-counter-gap 0` or `--require-exact` when the audit must chase every
remaining API-visible account instead of using the faster default gap. If fast
and exhaustive return the same `exported_count` while `visible_count` is higher,
report the result as Telegram API-visible maximum, not exact subscriber counter
equality.

Avoid broad Unicode sweeps by default; they are slow, trigger flood waits, and usually recover little or nothing. Use wider probes only when the user explicitly asks to chase missing counter-only accounts.

Known reference failure mode: one sample channel on 2026-05-11 returned `877/878` in both fast and exhaustive paths; the missing `1` was not exposed by recent participants, search slices, capped-slice split, admins, bots, or contacts.
