# Publication Checklist

- No `.env`, session files, archive DBs, Telegram Desktop `tdata`, generated
  registries, backups, logs, or downloaded media are committed.
- No machine-local absolute paths are required for a clean install.
- Plugin metadata points at the public repository.
- Default MCP allowlist excludes direct send/admin/delete tools.
- Unit tests pass for `mcp/` and `control-plane/`.
- Integration tests are green locally or any machine-local failures are
  documented before release.
- README explains Default Mode, Power Mode, and Operator Workflows without
  making Power Mode look hidden or unsupported.
- `SECURITY.md`, `CONTRIBUTING.md`, issue templates, PR template, and portable
  CI exist.
- Quickstart has been tested from a fresh clone or clean venv.
- Secret/path scan has been run before tagging.
