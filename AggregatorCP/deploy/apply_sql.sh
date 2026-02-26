#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNNER="${ROOT_DIR}/deploy/apply_sql.py"

DB_HOST="${DB_HOST:-127.0.0.1}"
DB_PORT="${DB_PORT:-3306}"
DB_USER="${DB_USER:-rathena}"
DB_PASS="${DB_PASS:-}"
DB_NAME="${DB_NAME:-ragnarok}"
MODE="${MODE:-auto}"
LANGUAGE="${LANGUAGE:-auto}"
APPLY_TOOLS="${APPLY_TOOLS:-}"
NO_PROMPT="${NO_PROMPT:-0}"
EMIT_SQL="${EMIT_SQL:-}"

if [[ ! -f "${RUNNER}" ]]; then
  echo "Missing Python SQL runner: ${RUNNER}" >&2
  exit 1
fi

PYTHON_BIN="${PYTHON_BIN:-python3}"
if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  echo "Python3 not found. Set PYTHON_BIN or install Python 3." >&2
  exit 1
fi

cmd=("${PYTHON_BIN}" "${RUNNER}" --db-host "${DB_HOST}" --db-port "${DB_PORT}" --db-user "${DB_USER}" --db-name "${DB_NAME}" --mode "${MODE}" --lang "${LANGUAGE}")
[[ -n "${DB_PASS}" ]] && cmd+=(--db-pass "${DB_PASS}")
[[ "${APPLY_TOOLS}" == "1" ]] && cmd+=(--apply-tools)
[[ "${APPLY_TOOLS}" == "0" ]] && cmd+=(--skip-tools)
[[ "${NO_PROMPT}" == "1" ]] && cmd+=(--no-prompt)
[[ -n "${EMIT_SQL}" ]] && cmd+=(--emit-sql "${EMIT_SQL}")

"${cmd[@]}"
