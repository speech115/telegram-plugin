"""Single source of truth for default Telegram MCP facade exposure."""

from __future__ import annotations

import json

from .tools import FACADE_TOOL_NAMES


def default_facade_tool_names() -> tuple[str, ...]:
    return tuple(sorted(FACADE_TOOL_NAMES))


def codex_mcp_servers_block(
    *,
    endpoint: str = "http://127.0.0.1:8799/mcp",
    token_env: str = "TELEGRAM_MCP_AUTH_TOKEN",
) -> dict[str, object]:
    return {
        "mcpServers": {
            "telegram-local": {
                "type": "http",
                "url": endpoint,
                "bearer_token_env_var": token_env,
                "note": "Local Telegram MCP server backed by telegram-mcp task-shaped facade tools.",
                "allowedTools": list(default_facade_tool_names()),
            }
        }
    }


def codex_mcp_json(
    *,
    endpoint: str = "http://127.0.0.1:8799/mcp",
    token_env: str = "TELEGRAM_MCP_AUTH_TOKEN",
) -> str:
    return json.dumps(codex_mcp_servers_block(endpoint=endpoint, token_env=token_env), indent=2) + "\n"