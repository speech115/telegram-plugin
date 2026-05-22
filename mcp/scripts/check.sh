#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PYTHON_BIN="${PROJECT_ROOT}/.venv/bin/python"
PYTHONPATH_VALUE="${PROJECT_ROOT}/src"

cd "${PROJECT_ROOT}"

if [ ! -x "${PYTHON_BIN}" ]; then
  printf 'Missing repo-local python at %s.\n' "${PYTHON_BIN}" >&2
  printf 'Bootstrap the local virtualenv with: uv pip install -e .\n' >&2
  exit 1
fi

printf 'Running unit tests...\n'
PYTHONPATH="${PYTHONPATH_VALUE}" \
"${PYTHON_BIN}" -m unittest discover -s tests -p 'test_*.py'

printf '\nRunning bytecode compilation...\n'
PYTHONPATH="${PYTHONPATH_VALUE}" \
"${PYTHON_BIN}" -m compileall src tests

printf '\nRunning smoke check...\n'
"${PROJECT_ROOT}/scripts/smoke-check.sh"

printf '\nAll checks passed.\n'
