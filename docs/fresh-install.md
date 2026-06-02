# Fresh Install Smoke

Use this checklist after cloning the repository on a new machine or before
tagging a release.

## One-command smoke (portable)

From the repository root:

```bash
./scripts/fresh-install-smoke.sh
```

This script:

- exports monorepo-local `TELEGRAM_*` paths (no `/Users/...` assumptions);
- bootstraps `mcp/.venv` and installs `telegram-mcp` editable;
- runs packaging hygiene scans on `plugin/`, `control-plane/`, and `mcp/src`;
- runs unit tests for `mcp/` and `control-plane/`;
- runs `telegram_mcp.release_gates` against `plugin/`;
- verifies `build-plugin-package` can copy `plugin/` into an empty directory;
- runs portable control-plane gates (`mcp-surface`, docs audit, adapter plan).

## Manual minimal path

```bash
git clone https://github.com/speech115/telegram-plugin.git
cd telegram-plugin

export TELEGRAM_MONOREPO_ROOT="$PWD"
export TELEGRAM_CONTROL_PLANE_ROOT="$PWD/control-plane"
export TELEGRAM_MCP_REPO="$PWD/mcp"
export TELEGRAM_PLUGIN_SOURCE="$PWD/plugin"
export TELEGRAM_PLUGIN_PACKAGE="$PWD/plugin"

cp mcp/.env.example mcp/.env
# fill TELEGRAM_API_ID / TELEGRAM_API_HASH, keep mcp/.env out of git

cd mcp && python3 -m venv .venv && .venv/bin/pip install -e .
cd ../control-plane && python3 -m pytest -q
cd .. && ./scripts/ci-release-gate.sh
```

## What CI runs

GitHub Actions job `release-gate` executes `./scripts/ci-release-gate.sh` on every
push/PR to `main`. Job `portable-tests` keeps the editable install + pytest path
for both packages.

## Not covered here

These require a configured host and are intentionally outside portable smoke:

- live Telegram login/session materialization;
- LaunchAgent daemon install;
- Codex plugin cache materialization (`codex plugin add`);
- mirror / telecrawl operator workflows.