# Default Mode demo

This is a sanitized example. It does not use real Telegram messages, usernames,
media files, sessions, or API tokens.

Default Mode is the normal path for agents. It lets an agent read, search,
collect context, prepare drafts, and inspect scoped local media. It does not
send messages or expose Telegram admin tools.

## Scenario

A maintainer wants an agent to catch up on a Telegram project chat and prepare a
reply, but not send anything.

```text
User:
Read today's chat with @example_project and summarize the decisions.
Do not send anything.
```

The agent uses the read-only facade first:

```text
resolve_dialog("@example_project")
read_today_dialog(dialog_ref="tg://dialog/channel/example-project", limit=30)
```

The answer should stay grounded in the returned messages:

```text
Summary:
- The team agreed to keep Default Mode read-only.
- The next release should update docs before changing runtime code.
- A demo should use fake messages and avoid screenshots from private chats.

Open question:
- Whether the demo belongs in README or in a separate docs page.
```

## Draft without sending

If the user asks for a reply, Default Mode prepares a draft only:

```text
User:
Draft a short reply saying that I agree with the docs-first plan.
```

The agent calls a preview tool:

```text
prepare_dialog_reply(
  dialog_ref="tg://dialog/channel/example-project",
  text="I agree with the docs-first plan. Let's keep the demo sanitized and avoid touching runtime code for this change."
)
```

The plugin returns a draft or preview. The message is not sent.

## What Default Mode blocks

These actions are outside the default plugin allowlist:

- sending a message
- replying in a live chat
- changing group or channel settings
- deleting messages
- exporting broad subscriber/member lists
- using a full Telegram admin surface

Power Mode can expose broader tools, but it requires explicit local setup. The
default plugin package should stay boring: read, search, draft, inspect, and
fail closed when the surface is unclear.

## Local checks

Before trusting a local install, run:

```bash
cd mcp
./bin/contract-smoke --json
./bin/contract-smoke --check-cache-stats --json
./bin/check-plugin-drift --json
```

Expected result: contract smoke succeeds and drift status is `ok`.
