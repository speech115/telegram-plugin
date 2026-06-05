# Telegram Control-Plane

Local operator layer that observes the Telegram stack, enforces read-only default MCP
surface rules, and fails closed when policy and runtime disagree.

## Language

**Control-plane**:
The repo at `tools/telegram` that audits, plans repairs, and packages the portable
plugin — not the live Telegram MCP runtime itself.
_Avoid_: Monorepo, telegram repo (when meaning only this tree)

**SurfaceContract**:
The policy-backed module (`policy/surface-contract.json` +
`surface_contract.py`) that classifies default MCP tools, validates plugin
allowlist parity, and checks control-plane docs for stale surface claims.
_Avoid_: Allowlist file, tool list in Python

**Default MCP surface**:
The restricted tool profile agents see through the installed plugin and local MCP
facade — read/search/prepare/confirmed-send only, never raw send/reply on default.
_Avoid_: Full MCP, admin profile (when meaning default)

**Confirmed write**:
A facade tool that may mutate Telegram only after an explicit preview token
(`telegram_confirmed_send`), not raw `send_*` / `reply_*` on the default surface.
_Avoid_: Write tool, send helper

**Live MCP**:
The `telegram-mcp` backend used for current/today/recent reads — not mirror or
Telecrawl archive evidence.
_Avoid_: Telegram API, Telethon (when meaning the managed backend path)

**ManagedSystems**:
The policy-backed topology (`policy/managed-systems.json` +
`managed_systems.py`) that registers every Telegram-related path, resolves
`paths.py` and shell wrappers from one inventory, and powers
`telegram-managed-systems` audits.
_Avoid_: Hardcoded paths in each script, duplicate path constants

**RegistryRedaction**:
The policy-backed persisted snapshot rules (`policy/registry-redaction.json` +
`registry_redaction.py`) that project allowlisted registry fields and block
private session, archive DB, and identity leaks in `observed-registry.json`.
_Avoid_: Copying raw audit payloads into generated registry files

**TelecrawlGapPolicy**:
The archive gap classifier (`policy/telecrawl.json` + `telecrawl_gap.py`) that
separates retryable import backlog from terminal access errors and marks known
gaps as operational warnings instead of release blockers.
_Avoid_: Treating every `import_errors` row as a live MCP failure

**SourceRouting**:
The evidence-routing policy (`policy/source-routing.json` + `source_routing.py`)
that maps natural-language intents to `live_mcp`, `telecrawl_archive`, or
`telegram_mirror` backends. CLI: `bin/telegram-source-route`.
_Avoid_: Using archive or mirror paths for today/latest/send without explicit intent

**RuntimeInventory**:
The aggregated launchd/session/mirror runtime view (`policy/runtime-inventory.json`
+ `runtime_inventory.py`) used by doctor for operator state without duplicating
child audits.
_Avoid_: Inspecting LaunchAgents and session trees ad hoc per task

**AuditRemediation**:
The repair-plan catalog (`policy/audit-remediation.json` + `audit_remediation.py`)
that links findings to ordered dry-run steps and keeps apply paths fail-closed.
_Avoid_: Ad-hoc cleanup commands without `telegram-repair-plan`