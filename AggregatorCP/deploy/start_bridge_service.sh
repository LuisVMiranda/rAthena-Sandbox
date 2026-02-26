#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"

"${PYTHON_BIN}" -m pip install -r "${ROOT_DIR}/bridge-service/requirements.txt"
exec "${PYTHON_BIN}" -m uvicorn app:app --app-dir "${ROOT_DIR}/bridge-service" --host 127.0.0.1 --port 8099
