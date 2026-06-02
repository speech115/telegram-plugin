#!/usr/bin/env bash
set -euo pipefail

if [[ "$#" -lt 1 ]]; then
  echo "usage: packaging-hygiene.sh <path> [<path> ...]" >&2
  exit 2
fi

failures=0

check_grep() {
  local label="$1"
  local root="$2"
  local matches
  matches="$(grep -RIn \
    --exclude-dir=.git \
    --exclude-dir=.venv \
    --exclude-dir=__pycache__ \
    --exclude-dir=node_modules \
    --exclude-dir=.pytest_cache \
    --exclude='*.png' \
    --exclude='*.jpg' \
    --exclude='*.svg' \
    --exclude='release_gates.py' \
    --exclude='plugin_package.py' \
    -E '/Users/sereja' \
    "$root" 2>/dev/null || true)"
  if [[ -n "${matches}" ]]; then
    printf 'packaging-hygiene: %s failed (%s)\n' "${label}" "${root}" >&2
    printf '%s\n' "${matches}" >&2
    failures=$((failures + 1))
  else
    printf 'packaging-hygiene: %s ok (%s)\n' "${label}" "${root}"
  fi
}

check_find() {
  local label="$1"
  local root="$2"
  local matches
  matches="$(find "$root" \
    \( -path '*/.git/*' -o -path '*/.venv/*' -o -path '*/__pycache__' -o -path '*/__pycache__/*' \) -prune -o \
    \( -name '*.pyc' -o -name '.env' -o -name '*.session' -o -name '.DS_Store' \) \
    -print 2>/dev/null || true)"
  if [[ -n "${matches}" ]]; then
    printf 'packaging-hygiene: %s forbidden artifacts (%s)\n' "${label}" "${root}" >&2
    printf '%s\n' "${matches}" >&2
    failures=$((failures + 1))
  else
    printf 'packaging-hygiene: forbidden-artifacts ok (%s)\n' "${root}"
  fi
}

for target in "$@"; do
  check_grep "text-scan" "${target}"
  check_find "tree-scan" "${target}"
done

if [[ "${failures}" -gt 0 ]]; then
  printf 'packaging-hygiene: %s check(s) failed\n' "${failures}" >&2
  exit 1
fi

printf 'packaging-hygiene: all checks passed\n'