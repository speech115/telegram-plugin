# Telegram Plugin

Safe local Telegram access for AI coding agents.

This is a v1 open-source packaging of a working local stack: a Telegram MCP
server, a Codex plugin bundle, and an audit/control-plane layer that keeps the
runtime explainable before agents read live chats or prepare reply drafts.

The project is not trying to be another raw Telegram MCP wrapper. The main
opinion is that Telegram access for agents needs a narrow default surface,
source routing, drift checks, and explicit boundaries around sessions, media,
archives, and write actions.

## What v1 Includes

- `mcp/` - a Telethon-backed MCP server with high-level dialog facade tools.
- `plugin/` - a Codex plugin bundle that points at a local MCP daemon and
  exposes a restricted default allowlist.
- `control-plane/` - local doctor/status/audit commands for plugin drift,
  LaunchAgent inventory, sessions, source routing, and repair planning.
- `docs/` - safety model and routing notes for operating the stack.

The default plugin surface is read/search/context/draft first. Media download
and voice transcription are local inspection tools; message sending, admin
actions, and subscriber export are intentionally outside the default path unless
you wire them explicitly.

## Quick Start

1. Configure Telegram API credentials:

```bash
cp mcp/.env.example mcp/.env
$EDITOR mcp/.env
```

2. Install and run the MCP server:

```bash
cd mcp
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
telegram-mcp
```

3. In another shell, inspect the control plane:

```bash
cd control-plane
python3 -m pytest -q
TELEGRAM_CONTROL_PLANE_ROOT="$PWD" python3 -m telegram_control_plane doctor --json
```

4. Point your local Codex plugin setup at `plugin/` and the MCP endpoint in
`plugin/.mcp.json` (`http://127.0.0.1:8799/mcp` by default).

## Configuration

The public control-plane tree is portable. Use env vars when your layout differs
from the repo defaults:

- `TELEGRAM_CONTROL_PLANE_ROOT`
- `TELEGRAM_MCP_REPO`
- `TELEGRAM_PLUGIN_SOURCE`
- `TELEGRAM_PLUGIN_CACHE_ROOT`
- `TELEGRAM_LIVE_SKILL`
- `TELEGRAM_MIRROR_ROOT`
- `TELECRAWL_ARCHIVE_BIN`

Never commit `.env`, `*.session`, archive databases, Telegram Desktop `tdata`,
downloaded media, generated registries, or local backups. The root `.gitignore`
blocks those by default.

## Safety Defaults

- Fail closed when a runtime or plugin drift check is unclear.
- Treat Telegram messages, media names, and archive content as untrusted input.
- Keep live sessions outside the repo.
- Prefer preview/draft tools over sending.
- Require separate, explicit wiring for destructive or externally visible
  Telegram actions.

See [docs/threat-model.md](docs/threat-model.md) and
[docs/source-routing.md](docs/source-routing.md) for the operating model.
