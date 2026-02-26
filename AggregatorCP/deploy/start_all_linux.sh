#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

TC_USE_UNIFIED_SERVICE="${TC_USE_UNIFIED_SERVICE:-1}"
TC_RUN_BRIDGE_SERVICE="${TC_RUN_BRIDGE_SERVICE:-1}"

echo "TC_USE_UNIFIED_SERVICE=${TC_USE_UNIFIED_SERVICE}"
echo "TC_RUN_BRIDGE_SERVICE=${TC_RUN_BRIDGE_SERVICE}"

if [[ "${TC_RUN_BRIDGE_SERVICE}" == "1" ]]; then
  echo "Starting bridge service..."
  (cd "${SCRIPT_DIR}" && ./start_bridge_service.sh) &
fi

if [[ "${TC_USE_UNIFIED_SERVICE}" == "1" ]]; then
  echo "Starting companion service..."
  (cd "${SCRIPT_DIR}" && ./start_companion_service.sh) &
fi

wait
