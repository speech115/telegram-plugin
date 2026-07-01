"""Interactive-by-invocation TDLib login for the isolated media-download POC.

pytdbot's Client.start() only auto-drives the authorization state machine
for bot-token logins (see pytdbot.Client.__handle_authorization_state_wait_phone_number,
which no-ops unless a bot token is set). For a real user account it does
nothing at authorizationStateWaitPhoneNumber, so this script drives the
state machine manually across multiple invocations, since a live phone/SMS
code can't be fed into a blocking input() call from outside a real TTY:

    uv run python benchmark/login_tdlib.py --phone +15551234567
    # (Telegram sends a login code to your other active sessions)
    uv run python benchmark/login_tdlib.py --code 12345
    # (only if the account has 2FA enabled)
    uv run python benchmark/login_tdlib.py --password ...

Each invocation reconnects to the same persistent session under data/tdlib/,
fully separate from the Telethon session telegram-mcp owns.
"""

import argparse
import asyncio
import os
from pathlib import Path

import pytdbot
from dotenv import load_dotenv

from benchmark.tdlib_client import build_client

POC_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = POC_ROOT / "data" / "tdlib"

_STATE_TO_REQUIRED_ARG = {
    "authorizationStateWaitPhoneNumber": "phone",
    "authorizationStateWaitCode": "code",
    "authorizationStateWaitPassword": "password",
}


def required_arg_for_state(state: str) -> str | None:
    return _STATE_TO_REQUIRED_ARG.get(state)


def raise_if_error(result):
    if isinstance(result, pytdbot.types.Error):
        raise RuntimeError(f"TDLib error {result['code']}: {result['message']}")
    return result


async def wait_for_stable_state(client: pytdbot.Client) -> str:
    for _ in range(20):
        state = client.authorization_state
        if state and state != "authorizationStateWaitTdlibParameters":
            return state
        await asyncio.sleep(0.5)
    return client.authorization_state


async def main(phone: str | None, code: str | None, password: str | None) -> None:
    load_dotenv(POC_ROOT / ".env")
    api_id = int(os.environ["TELEGRAM_API_ID"])
    api_hash = os.environ["TELEGRAM_API_HASH"]

    client = build_client(api_id=api_id, api_hash=api_hash, files_directory=str(DATA_DIR))
    await client.start(wait_login=False)

    state = await wait_for_stable_state(client)
    print(f"Current authorization state: {state}")

    required_arg = required_arg_for_state(state)
    supplied = {"phone": phone, "code": code, "password": password}.get(required_arg)

    if required_arg and not supplied:
        print(
            f"Need --{required_arg}. Re-run: "
            f"uv run python benchmark/login_tdlib.py --{required_arg} <value>"
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
