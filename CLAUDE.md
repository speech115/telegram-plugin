# Claude Code Notes

Canonical behavior contract for this repo is [`AGENTS.md`](AGENTS.md) — read
it first. This file adds Claude-specific context so a session that only
loads `CLAUDE.md` still has the essentials.

## Language
Respond in Russian. Code, git commit messages, and CLI output stay in English.

## Scope
Three coupled surfaces — prefer the more specific `mcp/AGENTS.md` /
`mcp/CLAUDE.md` and `control-plane/AGENTS.md` when working inside those
directories:
- `mcp/` — Telegram MCP server and live tool behavior.
- `control-plane/` — local operator commands, release checks, agent docs.
- `plugin/` — packaged Codex plugin and bundled Telegram skill.

## Developer Workflow (summary — see `AGENTS.md` for the full derivation)

- **Branch**: `claude/<topic-slug>` for work you start (mirrors the repo's
  established `codex/<topic-slug>` convention; do not invent another prefix).
- **Commit message**: single-line, capitalized, imperative summary
  (`Add X`, `Harden Y`) — no type prefix required; this repo doesn't use
  conventional commits consistently. Bullet body only for multi-part changes.
- **Attribution**: this repo's own history carries no `Co-Authored-By`
  trailers, but keep Claude Code's default trailer on commits you author —
  it's accurate disclosure, just don't backfill it onto older commits.
- **PR body**: `## Summary` (bullets) + `## Verification` (exact commands and
  real output, not "tests pass") + optional `## GitHub context`.
- **Before committing anything non-trivial**: run `scripts/safe-gate`. Quote
  its actual output in the PR, don't paraphrase.
- **main**: default path is branch -> PR, never push directly to `main`
  unless the user explicitly asks for that in the current request — an
  earlier approval to push doesn't carry forward.

## Commands

- `./scripts/safe-gate` — MCP tests + control-plane tests (portable mode) +
  agent docs sync drift + whitespace hygiene. Run before every non-trivial
  commit.
- `./scripts/ci-release-gate.sh` — full release verification.
- `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p 'test_*.py'`
  — run from `mcp/` directly when iterating on that surface. Zero extra deps.
  `CONTRIBUTING.md` shows `pytest` instead — that also works, but `pytest`
  isn't a declared dependency, so a fresh `.venv` needs
  `uv pip install pytest` before `uv run pytest` will find it.
