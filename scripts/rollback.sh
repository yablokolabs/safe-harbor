#!/usr/bin/env bash
# Safe Harbor — rollback.
#
# Software rollback and resident-state rollback are DIFFERENT operations
# and are never combined implicitly:
#
#   ./scripts/rollback.sh software [--bundle DIR]
#       Rebuild the SOFTWARE generation from a verified bundle. Resident
#       state is left untouched. Example: software generation N -> N-1
#       while resident state remains current.
#
#   ./scripts/rollback.sh state <backup-dir> [--yes]
#       Restore RESIDENT STATE from a validated backup. Software is left
#       untouched. Delegates to `safeharbor restore` (dry-run enforced).
#
# Before any risky upgrade or configuration change, create or require an
# appropriate recovery point (see runbooks/ROLLBACK.md).
set -Eeuo pipefail

MODE="${1:-}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
case "${MODE}" in
    software)
        BUNDLE_DIR="${2:-}"
        INSTALL="${SCRIPT_DIR}/../deploy/install.sh"
        if [[ -n "${BUNDLE_DIR}" ]]; then
            exec sudo "${INSTALL}" --bundle-dir "${BUNDLE_DIR}"
        fi
        exec sudo "${INSTALL}"
        ;;
    state)
        BACKUP_DIR="${2:-}"
        YES=0
        [[ "${3:-}" == "--yes" ]] && YES=1
        if [[ -z "${BACKUP_DIR}" ]]; then
            echo "usage: ./scripts/rollback.sh state <backup-dir> [--yes]" >&2
            exit 2
        fi
        if [[ "${YES}" == "1" ]]; then
            exec "${SCRIPT_DIR}/restore.sh" "${BACKUP_DIR}" --yes
        fi
        exec "${SCRIPT_DIR}/restore.sh" "${BACKUP_DIR}"
        ;;
    *)
        echo "usage: ./scripts/rollback.sh software [--bundle DIR] | state <backup-dir> [--yes]" >&2
        echo
        echo "software rollback and resident-state rollback are NEVER combined." >&2
        exit 2
        ;;
esac