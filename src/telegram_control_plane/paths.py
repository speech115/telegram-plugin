from __future__ import annotations

from pathlib import Path


HOME = Path("/Users/sereja")
CONTROL_ROOT = Path("/Users/sereja/Projects/tools/telegram")
MCP_REPO = Path("/Users/sereja/Projects/families/telegram/telegram-digest/telegram-mcp")
PLUGIN_SOURCE = Path("/Users/sereja/plugins/telegram")
PLUGIN_CACHE = Path("/Users/sereja/.codex/plugins/cache/sereja-local/telegram/0.1.3")
LIVE_SKILL = Path("/Users/sereja/.agents/skills/telegram")
MIRROR_ROOT = Path("/Users/sereja/Projects/tools/telegram-mirror")
MIRROR_LEGACY_ALIAS = Path("/Users/sereja/Projects/tools/hermes-agent-local/workspace/integrations/telegram-mirror")
TELECRAWL_ARCHIVE = Path("/Users/sereja/Projects/tools/agent-tooling/bin/telecrawl-archive")
LAUNCHAGENTS_DIR = HOME / "Library/LaunchAgents"
GENERATED_DIR = CONTROL_ROOT / "generated"
OBSERVED_REGISTRY = GENERATED_DIR / "observed-registry.json"
POLICY_DIR = CONTROL_ROOT / "policy"
