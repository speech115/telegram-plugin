"""One-time interactive TDLib login for the isolated media-download POC.

Run manually:
    uv run python benchmark/login_tdlib.py

This creates a TDLib session under data/tdlib/, fully separate from the
Telethon session telegram-mcp owns. It requires live phone-code entry for
the `main` account (confirmed with the operator before running this).
"""

import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv

from benchmark.tdlib_client import build_client

POC_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = POC_ROOT / "data" / "tdlib"


async def main() -> None:
    load_dotenv(POC_ROOT / ".env")
    api_id = int(os.environ["TELEGRAM_API_ID"])
    api_hash = os.environ["TELEGRAM_API_HASH"]

    client = build_client(api_id=api_id, api_hash=api_hash, files_directory=str(DATA_DIR))
    await client.start()
    me = await client.getMe()
    print(f"Logged in: {me}")
    await client.stop()


if __name__ == "__main__":
    asyncio.run(main())
