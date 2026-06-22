#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
RUNTIME_ROOT="${TELEGRAM_MUSIC_AUTOCLEAN_RUNTIME_ROOT:-/Users/sereja/Projects/runtime/telegram-music-autoclean}"
LABEL="com.sereja.telegram-music-autoclean"
GUI_DOMAIN="gui/$(id -u)"
TEMPLATE="$PROJECT_ROOT/scripts/launchagents/${LABEL}.plist.template"
DEST_DIR="$HOME/Library/LaunchAgents"
DEST_PLIST="$DEST_DIR/${LABEL}.plist"
SOURCE_SESSION="${TELEGRAM_MUSIC_AUTOCLEAN_SOURCE_SESSION:-$HOME/.telegram-mcp/session.session}"
RUNTIME_SESSION="$RUNTIME_ROOT/session/music_autoclean.session"
DRY_RUN=0
ALLOW_LIVE=0

usage() {
    echo "usage: $0 [--runtime-root PATH] [--dry-run] [--allow-live]" >&2
    exit 2
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --runtime-root)
            RUNTIME_ROOT="$2"
            RUNTIME_SESSION="$RUNTIME_ROOT/session/music_autoclean.session"
            shift 2
            ;;
        --dry-run)
            DRY_RUN=1
            shift
            ;;
        --allow-live)
            ALLOW_LIVE=1
            shift
            ;;
        -h|--help)
            usage
            ;;
        *)
            echo "unknown arg: $1" >&2
            usage
            ;;
    esac
done

RUNTIME_ROOT="$(python3 -c 'from pathlib import Path; import sys; print(Path(sys.argv[1]).expanduser().resolve())' "$RUNTIME_ROOT")"
RUNTIME_SESSION="$RUNTIME_ROOT/session/music_autoclean.session"

python3 - "$PROJECT_ROOT" "$RUNTIME_ROOT" <<'PY'
from pathlib import Path
import sys

project = Path(sys.argv[1]).resolve()
runtime = Path(sys.argv[2]).resolve()
if runtime == project:
    raise SystemExit("ERROR: runtime root must not equal project root")
try:
    runtime.relative_to(project)
except ValueError:
    pass
else:
    raise SystemExit("ERROR: runtime root must not live inside project root")
PY

if [ ! -f "$TEMPLATE" ]; then
    echo "ERROR: launchd template not found: $TEMPLATE" >&2
    exit 1
fi

if [ "$DRY_RUN" -eq 1 ]; then
    python3 -c "import json; print(json.dumps({'ok': True, 'mode': 'dry_run', 'label': '${LABEL}', 'plist': '${DEST_PLIST}', 'runtime_root': '${RUNTIME_ROOT}', 'runtime_session': '${RUNTIME_SESSION}', 'template': '${TEMPLATE}'}, ensure_ascii=False))"
    exit 0
fi

if [ "$ALLOW_LIVE" -ne 1 ] && [ "${TELEGRAM_MUSIC_AUTOCLEAN_ALLOW_LIVE:-0}" != "1" ]; then
    echo "ERROR: live launchd installation is disabled for $PROJECT_ROOT" >&2
    echo "Use --allow-live or TELEGRAM_MUSIC_AUTOCLEAN_ALLOW_LIVE=1 after dry-run verification." >&2
    exit 2
fi

if [ ! -f "$SOURCE_SESSION" ]; then
    echo "ERROR: source Telegram session not found: $SOURCE_SESSION" >&2
    exit 1
fi

mkdir -p "$DEST_DIR" "$RUNTIME_ROOT/logs" "$RUNTIME_ROOT/session" "$RUNTIME_ROOT/state"

if [ ! -f "$RUNTIME_SESSION" ]; then
    cp "$SOURCE_SESSION" "$RUNTIME_SESSION"
    chmod 600 "$RUNTIME_SESSION"
fi

escape_sed() {
    printf '%s' "$1" | sed -e 's/[\/&]/\\&/g'
}

HOME_ESCAPED="$(escape_sed "$HOME")"
PROJECT_ROOT_ESCAPED="$(escape_sed "$PROJECT_ROOT")"
RUNTIME_ROOT_ESCAPED="$(escape_sed "$RUNTIME_ROOT")"

sed \
    -e "s/__HOME__/${HOME_ESCAPED}/g" \
    -e "s/__PROJECT_ROOT__/${PROJECT_ROOT_ESCAPED}/g" \
    -e "s/__RUNTIME_ROOT__/${RUNTIME_ROOT_ESCAPED}/g" \
    "$TEMPLATE" > "$DEST_PLIST"

if ! plutil -lint "$DEST_PLIST" >/dev/null; then
    echo "ERROR: rendered plist is invalid: $DEST_PLIST" >&2
    plutil -lint "$DEST_PLIST"
    exit 1
fi

launchctl bootout "${GUI_DOMAIN}/${LABEL}" >/dev/null 2>&1 || true
launchctl bootout "$GUI_DOMAIN" "$DEST_PLIST" >/dev/null 2>&1 || true

launchctl bootstrap "$GUI_DOMAIN" "$DEST_PLIST"
launchctl kickstart -k "${GUI_DOMAIN}/${LABEL}"

echo "Installed and reloaded ${LABEL}"
echo "plist: $DEST_PLIST"
echo "runtime_root: $RUNTIME_ROOT"
