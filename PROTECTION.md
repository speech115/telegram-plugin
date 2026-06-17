# Telegram Protection Contract

Single-owner local rule:

Do not delete Telegram session directories, the MCP `.env`, or mirror runtime
state without explicit user approval and a recoverable backup or safe-trash
path.

The protected paths are listed in `policy/managed-systems.json`.
