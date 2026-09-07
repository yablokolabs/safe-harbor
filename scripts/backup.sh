#!/usr/bin/env bash
# Safe Harbor — operator backup wrapper.
#
#   ./scripts/backup.sh [--note "text"]
#
# Delegates to `safeharbor backup`. Safe for cron: never touches software,
# only persistent resident state, and only via the quiesce->stage->hash->
# manifest->publish flow in safeharbor/backup.py.
set -Eeuo pipefail

NOTE=""
if [[ "${1:-}" == "--note" ]]; then
    NOTE="${2:-}"
fi

if ! command -v safeharbor >/dev/null 2>&1; then
    echo "ERROR: safeharbor CLI not on PATH (run ./deploy/install.sh first)" >&2
    exit 1
fi

if [[ -n "${NOTE}" ]]; then
    exec safeharbor backup --note "${NOTE}"
fi
exec safeharbor backup