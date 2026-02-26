#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <rathena_tree> [install_subdir]" >&2
  exit 1
fi

TARGET_TREE="$(cd "$1" && pwd)"
INSTALL_SUBDIR="${2:-tools/traveler-companion}"
SOURCE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST_ROOT="${TARGET_TREE}/${INSTALL_SUBDIR}"

mkdir -p "${DEST_ROOT}"

rsync -a --delete \
  "${SOURCE_ROOT}/companion-service" \
  "${SOURCE_ROOT}/bridge-service" \
  "${SOURCE_ROOT}/sql-files" \
  "${SOURCE_ROOT}/docs" \
  "${SOURCE_ROOT}/deploy" \
  "${SOURCE_ROOT}/README.md" \
  "${DEST_ROOT}/"

echo "TravelerCompanion modules copied to: ${DEST_ROOT}"
echo "Next steps:"
echo "  1) Run ${DEST_ROOT}/deploy/apply_sql.sh with DB_* env vars."
echo "  2) Start companion-service (and bridge-service if needed) from ${DEST_ROOT}."
echo "  3) Open the web panel at http://127.0.0.1:4310 after service startup."
