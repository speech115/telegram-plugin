# Telegram Control-Plane Rules

- This directory is the local Telegram control-plane, not a Telegram runtime repo.
- Default operation is read-only toward external Telegram components.
- Do not move repos, refresh plugin cache, sync skill-index, rewrite LaunchAgents,
  start mirror jobs, or copy sessions from here without an explicit later plan.
- `generated/` may be rewritten by local doctor/status commands.
- The first milestone is allowed to fail closed on known defects.
