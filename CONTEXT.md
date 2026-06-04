# Telegram Control-Plane

Local operator layer that observes the Telegram stack, enforces read-only default MCP
surface rules, and fails closed when policy and runtime disagree.

## Language

**Control-plane**:
The repo at `tools/telegram` that audits, plans repairs, and packages the portable
plugin — not the live Telegram MCP runtime itself.
_Avoid_: Monorepo, telegram repo (when meaning only this tree)

**SurfaceContract**:
The policy-backed module (`policy/surface-contract.json` +
`surface_contract.py`) that classifies default MCP tools, validates plugin
allowlist parity, and checks control-plane docs for stale surface claims.
_Avoid_: Allowlist file, tool list in Python

**Default MCP surface**:
The restricted tool profile agents see through the installed plugin and local MCP
facade — read/search/prepare/confirmed-send only, never raw send/reply on default.
_Avoid_: Full MCP, admin profile (when meaning default)

**Confirmed write**:
A facade tool that may mutate Telegram only after an explicit preview token
(`telegram_confirmed_send`), not raw `send_*` / `reply_*` on the default surface.
_Avoid_: Write tool, send helper

**Live MCP**:
The `telegram-mcp` backend used for current/today/recent reads — not mirror or
Telecrawl archive evidence.
_Avoid_: Telegram API, Telethon (when meaning the managed backend path)