#!/usr/bin/env bash
# Safe Harbor — re-verify every acquired artifact against the lock manifest.
#
#   ./acquisition/verify.sh            verify all cached artifacts
#   ./acquisition/verify.sh --strict   fail if any artifact is missing
#
# Safe to run on the air-gapped target against a transferred cache: it never
# downloads anything.
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

if ! command -v python3 >/dev/null 2>&1; then
    echo "ERROR: python3 is required" >&2
    exit 1
fi

cd "${ROOT_DIR}"
exec python3 acquisition/acquire_core.py verify "${1:-}"