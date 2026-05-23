# Publication Checklist

- Version bumped in plugin/package metadata for this release.
- Changelog or release notes updated with user-visible changes.
- No `.env`, session files, archive DBs, Telegram Desktop `tdata`, generated
  registries, backups, logs, or downloaded media are committed.
- No machine-local absolute paths are required for a clean install.
- Plugin metadata points at the public repository.
- Default MCP allowlist excludes direct send/admin/delete tools.
- Contract smoke passes locally for release candidate:
  `./bin/contract-smoke --json` and `./bin/contract-smoke --check-cache-stats --json`.
- Plugin source/cache parity validated before release tag (no silent drift
  between `plugin/` source and materialized cache).
- Unit tests pass for `mcp/` and `control-plane/`.
- Integration tests are green locally or any machine-local failures are
  documented before release.
- README explains Default Mode, Power Mode, and Operator Workflows without
  making Power Mode look hidden or unsupported.
- `SECURITY.md`, `CONTRIBUTING.md`, issue templates, PR template, and portable
  CI exist.
- Quickstart has been tested from a fresh clone or clean venv.
- Secret/path scan has been run before tagging.
- Release is tagged (`vX.Y.Z`) and points to the commit used for release notes.
