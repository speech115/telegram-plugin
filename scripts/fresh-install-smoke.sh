#!/usr/bin/env bash
set -euo pipefail

# Simulates a fresh clone install: portable env, local venv bootstrap, no machine paths.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

printf 'fresh-install-smoke: repo=%s\n' "${ROOT}"
printf 'fresh-install-smoke: bootstrapping portable CI release gate\n'
"${ROOT}/scripts/ci-release-gate.sh"
printf 'fresh-install-smoke: passed\n'