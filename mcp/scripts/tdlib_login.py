"""Interactive-by-invocation TDLib login for the production `main`-account
media-download backend.

pytdbot's Client.start() only auto-drives the authorization state machine for
bot-token logins. For a real user account it does nothing at
authorizationStateWaitPhoneNumber, so this script drives the state machine
manually across multiple invocations, since a live phone/SMS code can't be fed
into a blocking input() call from outside a real TTY:

    PYTHONPATH=src .venv/bin/python scripts/tdlib_login.py --phone +15551234567
    # (Telegram sends a login code to your other active sessions)
    PYTHONPATH=src .venv/bin/python scripts/tdlib_login.py --code 12345
    # (only if the account has 2FA enabled)
    PYTHONPATH=src .venv/bin/python scripts/tdlib_login.py --password ...

Each invocation reconnects to the same persistent session under
TELEGRAM_TDLIB_SESSION_DIR (default ~/.telegram-mcp-tdlib/main), fully
separate from the Telethon session tree telegram-mcp owns.

Requires the optional tdlib extra: pip install -e ".[tdlib]"
"""

import argparse
import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv

from telegram_mcp.tdlib_download import build_client, raise_if_error

_STATE_TO_REQUIRED_ARG = {
    "authorizationStateWaitPhoneNumber": "phone",
    "authorizationStateWaitCode": "code",
    "authorizationStateWaitPassword": "password",
}


def required_arg_for_state(state: str) -> str | None:
    return _STATE_TO_REQUIRED_ARG.get(state)


async def wait_for_stable_state(client) -> str:
    for _ in range(20):
        state = client.authorization_state
        if state and state != "authorizationStateWaitTdlibParameters":
            return state
        await asyncio.sleep(0.5)
    return client.authorization_state


async def main(phone: str | None, code: str | None, password: str | None) -> None:
    load_dotenv(Path.home() / ".telegram-mcp" / "launchd.env")
    api_id = int(os.environ["TELEGRAM_API_ID"])
    api_hash = os.environ["TELEGRAM_API_HASH"]
    session_dir = Path(
        os.environ.get("TELEGRAM_TDLIB_SESSION_DIR", "~/.telegram-mcp-tdlib/main")
    ).expanduser()

    client = build_client(api_id=api_id, api_hash=api_hash, files_directory=str(session_dir))
    await client.start(wait_login=False)

    state = await wait_for_stable_state(client)
    print(f"Current authorization state: {state}")

    required_arg = required_arg_for_state(state)
    supplied = {"phone": phone, "code": code, "password": password}.get(required_arg)

    if required_arg and not supplied:
        print(
            f"Need --{required_arg}. Re-run: "
            f"PYTHONPATH=src .venv/bin/python scripts/tdlib_login.py --{required_arg} <value>"
        )
        await client.stop()
        return

    if state == "authorizationStateWaitPhoneNumber":
        raise_if_error(await client.setAuthenticationPhoneNumber(phone_number=phone))
        print("Code requested. Check Telegram on your other devices, then run with --code.")
    elif state == "authorizationStateWaitCode":
        raise_if_error(await client.checkAuthenticationCode(code=code))
        print("Code accepted.")
    elif state == "authorizationStateWaitPassword":
        raise_if_error(await client.checkAuthenticationPassword(password=password))
        print("Password accepted.")
    elif state == "authorizationStateReady":
        me = raise_if_error(await client.getMe())
        print(f"Already logged in: {me}")

    await asyncio.sleep(1)
    print(f"Authorization state now: {client.authorization_state}")
    await client.stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--phone")
    parser.add_argument("--code")
    parser.add_argument("--password")
    args = parser.parse_args()
    asyncio.run(main(args.phone, args.code, args.password))
