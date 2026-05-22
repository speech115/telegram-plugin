# Publication Checklist

- No `.env`, session files, archive DBs, Telegram Desktop `tdata`, generated
  registries, backups, logs, or downloaded media are committed.
- No machine-local absolute paths are required for a clean install.
- Plugin metadata points at the public repository.
- Default MCP allowlist excludes direct send/admin/delete tools.
- Unit tests pass for `mcp/` and `control-plane/`.
- Secret/path scan has been run before tagging.
