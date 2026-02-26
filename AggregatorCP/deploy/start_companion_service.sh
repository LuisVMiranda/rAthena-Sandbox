#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_DIR="${SCRIPT_DIR}/../companion-service"
: "${TC_COMPANION_CONFIG:=${HOME}/.config/traveler-companion/config.json}"
export TC_COMPANION_CONFIG
mkdir -p "$(dirname "${TC_COMPANION_CONFIG}")"

python3 -m pip install -r "${SERVICE_DIR}/requirements.txt"
python3 -m uvicorn app:app --app-dir "${SERVICE_DIR}" --host 127.0.0.1 --port 4310
