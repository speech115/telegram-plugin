# Telegram Plugin

Safe local Telegram access for AI coding agents.

This is an alpha open-source packaging of a working local stack: a Telegram MCP
server, a Codex plugin bundle, and an optional audit/control-plane layer that
keeps the runtime explainable before agents read live chats or prepare reply
drafts.

The project is not trying to be another raw Telegram MCP wrapper. The main
opinion is that Telegram access for agents needs a narrow default surface,
source routing, drift checks, and explicit boundaries around sessions, media,
archives, and write actions.

## What v0.1 Alpha Includes

- `mcp/` - a Telethon-backed MCP server with high-level dialog facade tools.
- `plugin/` - a Codex plugin bundle that points at a local MCP daemon and
  exposes a restricted default allowlist.
- `control-plane/` - optional local doctor/status/audit commands for plugin
  drift, LaunchAgent inventory, sessions, source routing, and repair planning.
- `docs/` - safety model and routing notes for operating the stack.

Default Mode is read/search/context/draft first. Media download
and voice transcription are local inspection tools; message sending, admin
actions, and subscriber export are intentionally outside the default path unless
you wire them explicitly.

The project has three operating modes:

| Mode | Use it for | Can change Telegram? | Default |
| --- | --- | --- | --- |
| Default Mode | read, search, context, drafts, previews, scoped media, voice transcription | No direct writes | Yes |
| Power Mode | full MCP surface: send/reply, contacts, groups/channels, stories, profile, privacy state | Yes | No |
| Operator Workflows | mirror/archive, subscriber export, control-plane repair and audits | Can read in bulk or create sensitive artifacts | No |

Power Mode is not a weaker or hidden product. It is the explicit mode for users
who want the whole Telegram MCP surface and accept that agents can perform
externally visible actions.

## Quick Start

1. Configure Telegram API credentials:

```bash
cp mcp/.env.example mcp/.env
$EDITOR mcp/.env
```

2. Install and run the MCP server:

```bash
cd mcp
uv venv
uv pip install -e .
.venv/bin/telegram-mcp
```

3. In another shell, inspect the control plane:

```bash
cd control-plane
uv venv
uv pip install -e . pytest
.venv/bin/python -m pytest -q
TELEGRAM_CONTROL_PLANE_ROOT="$PWD" .venv/bin/python -m telegram_control_plane doctor --json --no-write
```

4. Run the local contract smoke after the daemon is up:

```bash
cd mcp
./bin/contract-smoke --profile all --check-cache-stats --json
```

5. Point your local Codex plugin setup at `plugin/` and the MCP endpoint in
`plugin/.mcp.json` (`http://127.0.0.1:8799/mcp` by default).

To inspect the full server surface locally, run the daemon with:

```bash
TELEGRAM_MCP_TOOL_PROFILE=full .venv/bin/telegram-mcp
```

Use `plugin/.mcp.full.example.json` only when you intentionally want Power Mode
in a local agent client.

## Configuration

The MCP server and plugin bundle are the portable default path. The
control-plane is useful for local operators, but parts of it inspect
machine-local LaunchAgents, sessions, plugin caches, mirror state, and archive
wrappers. A red control-plane doctor means the local machine inventory needs
attention; it does not necessarily mean the default MCP plugin surface is broken.

Use env vars when your local layout differs from the repo defaults:

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

## Capability Boundaries

- Default Mode: live read/search/context/draft/preview, scoped local media
  download, and selected voice/video transcription.
- Power Mode: broader Telegram API operations, including writes, contacts,
  groups/channels, stories, profile, and privacy state. This is opt-in and not
  enabled by the Default Mode allowlist.
- Operator Workflows: mirror/archive/subscriber export/control-plane work. These
  are not Default Mode functions and require their own setup and safety checks.

## Safety Defaults

- Fail closed when a runtime or plugin drift check is unclear.
- Treat Telegram messages, media names, and archive content as untrusted input.
- Keep live sessions outside the repo.
- Prefer preview/draft tools over sending.
- Require separate, explicit wiring for destructive or externally visible
  Telegram actions.

See [docs/threat-model.md](docs/threat-model.md) and
[docs/source-routing.md](docs/source-routing.md) for the operating model. See
[docs/operator-workflows.md](docs/operator-workflows.md) before using Power Mode,
mirror/archive, or subscriber-export workflows.
