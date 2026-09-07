#!/usr/bin/env bash
# Safe Harbor — assemble the verified offline bundle.
#
#   ./acquisition/assemble.sh
#
# Refuses to assemble until every locked artifact is present and verified.
# Produces dist/safe-harbor-gen1-<version>-<arch>.tar.gz plus its .sha256.
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

if ! command -v python3 >/dev/null 2>&1; then
    echo "ERROR: python3 is required" >&2
    exit 1
fi

cd "${ROOT_DIR}"
exec python3 acquisition/acquire_core.py assemble