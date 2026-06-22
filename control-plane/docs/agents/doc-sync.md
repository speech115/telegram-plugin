# Doc Sync (skill ↔ MCP resources)

Edit `plugin/skills/telegram/references/`, then:

```bash
./bin/telegram-agent-docs-sync
```

Restarts local MCP HTTP daemons automatically after sync. CI uses `--check --no-restart`.
`build-plugin-package` runs the same sync automatically. Manifest:
`skills/telegram/agent-docs/manifest.json`.
