"""Telegram MCP server for Claude Code."""

from .telethon_compat import apply_telethon_compat

apply_telethon_compat()

from . import mcp_prewarm as mcp_prewarm  # noqa: E402,F401
