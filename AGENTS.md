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
  behavior in that specific request. A prior approval to push does not carry
  forward to later sessions or later commits — ask again each time.
- Do not merge PRs, close issues, post public GitHub comments, tag, or release
  without a separate explicit user request.

## Developer Workflow Conventions

Derived from this repo's actual commit/PR history (`git log`, `gh pr list`),
not just the templates. Follow the observed pattern, not an invented one.

**Branch naming** — prefix by session origin, then a kebab-case topic slug:
- `codex/<topic-slug>` — dominant pattern for Codex CLI sessions (e.g.
  `codex/control-plane-operator-gates`, `codex/thermonuclear-fixes`).
- `claude/<topic-slug>` — use this for Claude Code sessions; no Claude-specific
  prefix existed before, this mirrors the established `codex/` convention so
  branch origin stays identifiable.
- `docs/issue-<n>-<topic-slug>` — docs-only PRs that close a numbered issue.

**Commit messages** — single-line, capitalized, imperative, verb-first summary
(`Harden Telegram MCP control surfaces`, `Add Telegram metadata fast lane`).
No conventional-commit type prefix is required or consistently used — only
2 of the last 24 commits use one (`Chore: ...`, `docs: ...`), so don't invent
a strict `feat:`/`fix:` scheme. For multi-part changes, add a body with `-`
bullets (mirrors what a squashed PR's `## Summary` becomes). Squash-merged PRs
get GitHub's `(#<n>)` suffix automatically — don't add it by hand on direct
commits.

**Attribution** — 22 of the last 24 commits in this repo carry no co-author
trailer at all; this repo has not historically used `Co-Authored-By`. Claude
Code's own default behavior appends a `Co-Authored-By: Claude ... <noreply@anthropic.com>`
trailer on commits it authors — keep doing that for Claude-authored commits
(it accurately discloses tooling and costs nothing), but don't backfill it
onto older Codex-authored history or expect it there.

**PR body structure** — two header variants appear, use this shape:
```
## Summary
- one bullet per change

## Verification
- exact command(s) run
- actual result, not "tests pass" (e.g. "control-plane 204 passed, MCP 337 tests OK")
```
Add an optional `## GitHub context` section when the PR interacts with CI
state or another open PR (see PR #13). This should satisfy
`.github/PULL_REQUEST_TEMPLATE.md`'s checklist directly — fill it in, don't
leave it as unchecked boilerplate.

**Test plan / evidence** — run `scripts/safe-gate` before every non-trivial
commit (see Local Gate below); quote real test counts in the PR, not vague
claims. For live-behavior changes, also run local live smoke and paste
redacted output per `CONTRIBUTING.md`.

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
