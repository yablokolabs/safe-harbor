#!/usr/bin/env bash
# Safe Harbor — Stage A acquisition (connected machine only).
#
#   ./acquisition/acquire.sh            download + verify every locked artifact
#   ./acquisition/acquire.sh --if-missing   only fetch artifacts not already cached
#
# The artifact list, URLs, versions and SHA-256 hashes are read exclusively
# from manifest/artifacts.lock. This script never decides anything itself.
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

if ! command -v python3 >/dev/null 2>&1; then
    echo "ERROR: python3 is required on the acquisition machine" >&2
    exit 1
fi

cd "${ROOT_DIR}"
if [[ "${1:-}" == "--if-missing" ]]; then
    exec python3 acquisition/acquire_core.py acquire --if-missing
fi
exec python3 acquisition/acquire_core.py acquire