# 03 — P2 stability gates

**Status:** ready-for-human

## Shipped

- CI: `mcp-surface`, `source-routing-audit` in `policy/release-gates.json` ci mode
- Expanded `test_source_routing.py` + audit samples for today intents
- `intent_router.format_contract_error` — single next action on live/archive violations
- `facade-routing.md` HTTP MCP session section (shared client, stateless caveat)

## Verify

```bash
./bin/telegram-release-gate --ci
python3 -m pytest tests/test_source_routing.py -q
```