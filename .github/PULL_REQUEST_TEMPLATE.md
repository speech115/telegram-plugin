## Summary

## Layer

- [ ] Default Mode
- [ ] MCP server
- [ ] Power Mode
- [ ] Control-plane
- [ ] Operator Workflows
- [ ] Mirror/archive
- [ ] Subscriber export
- [ ] Documentation
- [ ] Tests/CI

## Checks

- [ ] `mcp/.venv/bin/python -m pytest -q`
- [ ] `mcp/.venv/bin/python -m compileall -q src tests`
- [ ] `control-plane/.venv/bin/python -m pytest -q`
- [ ] `control-plane/.venv/bin/python -m compileall -q src tests`
- [ ] Local live smoke, if relevant

## Safety

- [ ] No credentials, sessions, private Telegram content, media, archive DBs, or subscriber exports are committed.
- [ ] Default Mode allowlist remains read/search/context/draft/preview/media/voice only.
- [ ] Any Power Mode or Operator Workflow behavior is explicit and documented.
