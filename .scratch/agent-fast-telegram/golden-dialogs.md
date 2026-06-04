# Golden dialogs (from local evidence)

Sources: `~/telegram-mcp/telemetry/daily/*.jsonl`, `notes-skill/config.json`, live `resolve_dialog` (2026-06-04).

## Confirmed recent agent/tool usage

| Handle for `tg read today` | Resolved title | Type | Last seen (UTC) | Evidence |
| --- | --- | --- | --- | --- |
| `me` | Сергей Иванов (@CrwDdy) | Saved / self | 2026-06-04 17:02 | 18× `telegram_read` / `fast_read` / smoke |
| `-1003850136767` | **Конспекты** | Channel | 2026-06-04 16:30 | 3× `send_file` (notes-skill) |
| `tg://dialog/user/7091037467` | (same as `me`) | User | 2026-06-02 19:32 | `telegram_confirmed_send` tests |

## Config (active, not necessarily read)

- `notes-skill`: delivery chat `-1003850136767` → **Конспекты**

## Mirror allowlist (your channels; not in recent read telemetry)

From `runtime/telegram-mirror/data/telegram_sync/mirrors.json`:

- ПРАЙМ (`-1003740929123`)
- ПРАЙМ ЧАТ (`-1003846910462`)
- Оберег (`-1003236172687`, forum group)
- Dreamer (`-1001893068117`)
- VERSHININ (`-1003796652583`)
- Секта Капитализма (`-1003712410697`)

## User golden set (1:1, added 2026-06-04)

| Handle for `tg read today` | Resolved name | Username | `dialog_ref` |
| --- | --- | --- | --- |
| `@commercialclub` | Илья Кудрис | *(contact; resolve matched @commercialclub)* | `tg://dialog/user/862547783` |
| `@AndrewBTO` | Андрей Чуманенко | `AndrewBTO` | `tg://dialog/user/1856687999` |
| `@brexit_man` | Brexit | `brexit_man` | `tg://dialog/user/307872069` |

Canonical manifest: `policy/golden-dialogs.json` (runner: `./bin/telegram-golden-read-smoke`).

## Suggested regression set

```bash
tg read today me --limit 30 --json
tg read today @commercialclub --limit 30 --json
tg read today @AndrewBTO --limit 30 --json
tg read today @brexit_man --limit 30 --json
tg read today -1003850136767 --limit 30 --json
```

Expect `payload.data_source == "live_telegram"` on each.