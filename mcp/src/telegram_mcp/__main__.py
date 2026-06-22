"""Entry point: login or serve."""

import sys

from .telethon_compat import apply_telethon_compat

apply_telethon_compat()

from .auth import run_doctor, run_health, run_login


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "login":
        run_login()
    elif len(sys.argv) > 1 and sys.argv[1] == "health":
        run_health()
    elif len(sys.argv) > 1 and sys.argv[1] == "doctor":
        run_doctor()
    else:
        from .server import run_server
        run_server()


if __name__ == "__main__":
    main()
