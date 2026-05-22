#!/bin/bash
# Rotate telegram-mcp logs. Keep last 3 rotations, max 1MB each.
LOG="${TELEGRAM_MCP_LOG:-$HOME/Library/Logs/telegram-mcp/http-launchd.log}"
MAX_SIZE=1048576  # 1MB

[ ! -f "$LOG" ] && exit 0

size=$(stat -f%z "$LOG" 2>/dev/null || echo 0)
[ "$size" -lt "$MAX_SIZE" ] && exit 0

# Rotate
[ -f "${LOG}.2" ] && rm -f "${LOG}.2"
[ -f "${LOG}.1" ] && mv "${LOG}.1" "${LOG}.2"
cp "$LOG" "${LOG}.1"
: > "$LOG"
