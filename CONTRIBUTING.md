# Contributing

This project is alpha and intentionally conservative. The most useful
contributions improve the safe default path, setup reliability, tests,
documentation, and security boundaries.

## Local Checks

Run portable checks before opening a PR:

```bash
cd mcp
uv venv
uv pip install -e . pytest
.venv/bin/python -m pytest -q
.venv/bin/python -m compileall -q src tests

cd ../control-plane
uv venv
uv pip install -e . pytest
.venv/bin/python -m pytest -q
.venv/bin/python -m compileall -q src tests
```

Live checks require a local Telegram session and should not run in public CI:

```bash
cd mcp
./bin/contract-smoke --profile all --check-cache-stats --json

cd ../control-plane
.venv/bin/python -m pytest -q -m integration
```

## Contribution Boundaries

- Keep Default Mode read/search/context/draft/preview/media/voice only.
- Do not add write/admin/destructive tools to `plugin/.mcp.json`.
- Keep Power Mode opt-in.
- Keep mirror/archive/subscriber export as Operator Workflows with explicit setup
  and safety checks.
- Do not commit credentials, sessions, private Telegram content, media,
  generated registries, archive databases, or subscriber exports.

## Pull Request Checklist

- Explain which layer changed: Default Mode, MCP server, Power Mode,
  control-plane, mirror/archive, subscriber export, docs, or tests.
- Include test output for affected portable checks.
- For live behavior changes, include redacted local smoke output.
- Update docs when behavior or setup changes.
- Confirm no private Telegram data or machine-local secrets were added.
