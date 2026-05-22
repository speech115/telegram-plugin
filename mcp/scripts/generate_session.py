"""Generate a Telegram session string (alternative to file-based session)."""

import asyncio
import sys

from telethon import TelegramClient
from telethon.sessions import StringSession


async def generate() -> None:
    api_id = input("Enter API ID: ").strip()
    api_hash = input("Enter API Hash: ").strip()

    client = TelegramClient(StringSession(), int(api_id), api_hash)
    await client.start()

    session_string = client.session.save()
    print(f"\nSession string:\n{session_string}")
    print("\nStore this securely. You can use it as TELEGRAM_SESSION_STRING env var.")

    await client.disconnect()


if __name__ == "__main__":
    try:
        asyncio.run(generate())
    except KeyboardInterrupt:
        print("\nCancelled.")
        sys.exit(1)
