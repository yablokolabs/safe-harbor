#!/usr/bin/env bash
# Safe Harbor — operator restore wrapper.
#
#   ./scripts/restore.sh <backup-dir>            dry-run + interactive confirm
#   ./scripts/restore.sh <backup-dir> --yes      non-interactive (CI)
#
# Restore is destructive by nature. The wrapper ALWAYS runs the dry-run
# validation first and refuses to proceed when the backup is corrupt or
# incomplete. Software rollback is a DIFFERENT operation (see rollback.sh);
# they are never combined implicitly.
set -Eeuo pipefail

BACKUP_DIR="${1:-}"
YES=0
[[ "${2:-}" == "--yes" ]] && YES=1

if [[ -z "${BACKUP_DIR}" ]]; then
    echo "usage: ./scripts/restore.sh <backup-dir> [--yes]" >&2
    exit 2
fi
if ! command -v safeharbor >/dev/null 2>&1; then
    echo "ERROR: safeharbor CLI not on PATH" >&2
    exit 1
fi

echo "== dry-run validation =="
if ! safeharbor restore --dry-run "${BACKUP_DIR}"; then
    echo "restore REFUSED — see problems above" >&2
    exit 1
fi

if [[ "${YES}" == "1" ]]; then
    exec safeharbor restore --yes "${BACKUP_DIR}"
fi

echo
echo "Dry-run passed. Proceeding to interactive restore..."
exec safeharbor restore "${BACKUP_DIR}"