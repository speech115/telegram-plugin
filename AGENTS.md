# Telegram Plugin Repo Rules

## Scope

This repo contains three coupled surfaces:

- `mcp/`: Telegram MCP server and live tool behavior.
- `control-plane/`: local operator commands, release checks, and agent docs.
- `plugin/`: packaged Codex plugin and bundled Telegram skill.

Prefer the more specific `mcp/AGENTS.md` and `control-plane/AGENTS.md` when
working inside those directories.

## GitHub Workflow

- Use the `github-radar` skill before PR, merge, release, or issue cleanup work.
- Use the `git-safe-workflow` skill for commits and PRs.
- Default path is branch -> local checks -> exact-file commit -> PR.
- Do not push directly to `main` unless the user explicitly asks for direct-main
  behavior.
- Do not merge PRs, close issues, post public GitHub comments, tag, or release
  without a separate explicit user request.

## Local Gate

Run `scripts/safe-gate` before committing non-trivial changes. It checks:

- whitespace diff hygiene;
- MCP tests;
- control-plane tests in portable mode;
- agent docs sync drift.

For full release verification, run `scripts/ci-release-gate.sh`.

## Product Safety

- Keep Telegram read-surface expansion read-only by default.
- Do not add read-state mutators, direct sends, cache sync, session copying,
  LaunchAgent rewrites, or mirror jobs without an explicit request.
- After MCP tool surface changes, run `mcp/bin/sync-agent-docs --plugin-dir plugin --no-restart --json`.
- A clean plugin drift report is not enough; verify the actual runtime/tool
  surface when the change affects MCP behavior.
