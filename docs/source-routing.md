# Source Routing

The stack separates Telegram sources by freshness and risk.

## Live MCP

Use the live MCP daemon when the task depends on current Telegram state, recent
messages, or exact reply context. This path needs Telegram credentials and a
valid session outside the repo.

## Mirror

A mirror can be useful for repeated read-heavy analysis, but it is not the
default authority for "latest" claims unless its freshness has been proven for
the target dialog.

## Archive

Archives are historical search aids. They can surface candidates and old
context, but coverage gaps and inactive accounts must be visible to the agent.
Archive results should be labeled as archive-derived.

## Routing Rule

Use the narrowest source that can answer the question:

- live MCP for current or user-visible decisions;
- mirror for verified local snapshots;
- archive for historical lexical search;
- control-plane audits when deciding whether any of the above can be trusted.
