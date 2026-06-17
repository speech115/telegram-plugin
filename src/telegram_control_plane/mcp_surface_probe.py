from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Iterable

from .paths import MCP_REPO


def live_mcp_surface_probe(
    required_tools: Iterable[str],
    *,
    accounts: Iterable[str] = ("main", "pl"),
    mcp_repo: Path = MCP_REPO,
) -> dict[str, Any]:
    python_bin = mcp_repo / ".venv/bin/python"
    if not python_bin.exists():
        return {
            "status": "fail",
            "error": f"missing MCP Python runtime: {python_bin}",
            "accounts": {},
        }

    account_names = tuple(str(account) for account in accounts)
    script = f"""
import asyncio
import json
import sys

sys.path.insert(0, {str(mcp_repo / "src")!r})
from telegram_mcp.mcp_http_client import call_tool_with_failover, list_tools_with_failover

required = {sorted(str(tool) for tool in required_tools)!r}
accounts = {account_names!r}

async def main():
    async def probe(account):
        names, list_elapsed, list_attempt = await list_tools_with_failover(account=account, timeout=8)
        me_result, me_elapsed, me_attempt = await call_tool_with_failover(
            tool_name="get_me",
            arguments={{}},
            account=account,
            timeout=8,
        )
        missing = sorted(set(required) - set(names))
        return account, {{
            "status": "ok" if not missing and me_result is not None else "fail",
            "tool_count": len(names),
            "missing_required_tools": missing,
            "get_me_ok": me_result is not None,
            "list_endpoint": list_attempt.endpoint,
            "get_me_endpoint": me_attempt.endpoint,
            "list_elapsed_seconds": list_elapsed,
            "get_me_elapsed_seconds": me_elapsed,
        }}
    results = await asyncio.gather(*(probe(account) for account in accounts))
    out = dict(results)
    print(json.dumps({{"status": "ok", "accounts": out}}, ensure_ascii=False))

asyncio.run(main())
"""
    completed = subprocess.run(
        [str(python_bin), "-c", script],
        text=True,
        capture_output=True,
        check=False,
        timeout=25,
    )
    if completed.returncode != 0:
        return {
            "status": "fail",
            "error": completed.stderr.strip() or completed.stdout.strip() or "live MCP probe failed",
            "exit_code": completed.returncode,
            "accounts": {},
        }
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        return {
            "status": "fail",
            "error": f"live MCP probe returned invalid JSON: {exc}",
            "stdout": completed.stdout,
            "accounts": {},
        }
    if isinstance(payload, dict):
        return payload
    return {"status": "fail", "error": "live MCP probe returned non-object", "accounts": {}}
