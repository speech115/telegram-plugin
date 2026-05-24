# Source Evidence Broker

Use one Telegram front door, but keep claims source-labeled.

## Labels Vs Tooling

- `telegram_mirror` is the evidence label for allowlisted mirrored data.
- `telegram-local-mirror` is the skill/tooling route that can access mirror and
  telecrawl-backed historical reads.
- `telecrawl_archive` is the evidence label for archive snapshot search results.
- `telecrawl-archive` is the CLI used for archive readiness, search, coverage,
  and context commands.

## Source Types

- `live_mcp`: current Telegram state, `today/latest/recent`, exact live reads, send/reply, media download, and voice transcription.
- `telegram_mirror`: allowlist-only mirrored channels/dialogs, watcher-backed cache, enriched historical context, media enrichment, and operator/fidelity checks.
- `telecrawl_archive`: broad historical lexical candidate search through `<agent-tooling-repo>/bin/telecrawl-archive`.

`telecrawl_archive` is an archive snapshot, not live Telegram. Do not use it as the primary source for `today`, `latest`, `recent`, current state, send/reply, or media inspection.

`telegram_mirror` is allowlist/registry-only. If the target is not allowlisted, use live MCP for current/scoped work or telecrawl for broad historical lexical search.

## Telecrawl Readiness

Before relying on telecrawl, run:

```bash
<agent-tooling-repo>/bin/telecrawl-archive accounts
<agent-tooling-repo>/bin/telecrawl-archive status
<agent-tooling-repo>/bin/telecrawl-archive errors --limit 20
```

Treat `archive_ready=false`, missing or in-progress manifests, count mismatches, stale per-chat coverage, or known import gaps as blockers for completeness claims.

For broad cross-account recall:

```bash
<agent-tooling-repo>/bin/telecrawl-archive search-all "<query>" --limit 20
```

For chat-scoped coverage:

```bash
<agent-tooling-repo>/bin/telecrawl-archive coverage --chat <chat-id-or-name>
<agent-tooling-repo>/bin/telecrawl-archive context --chat <chat-id> --msg-id <message-id> --before 5 --after 5
```

If coverage returns `ambiguous_chat_match`, resolve by numeric chat id before making scoped claims.

## Labels To Carry Forward

When telecrawl evidence matters, include:

- `source`: `telecrawl`
- `source_kind`: `archive_snapshot`
- `coverage_claim`
- `last_complete_import_at`
- `chat_last_message_at` when available
- `confidence`: usually `candidate` until live/mirror verification confirms more
- `identity_confidence`: source-specific unless stable peer id or unique username resolves identity

Negative results from telecrawl mean only "no matches in this archive coverage". Do not say "not found in Telegram" unless the live or mirror scope needed for that claim was also checked.
