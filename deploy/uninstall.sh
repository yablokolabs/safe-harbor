#!/usr/bin/env bash
# Safe Harbor Gen1 — uninstall.
#
# Removes SOFTWARE and configuration but NEVER removes persistent resident
# state by default. A destructive purge is a distinct, explicit operation:
#
#   sudo ./deploy/uninstall.sh            safe uninstall (resident state kept)
#   sudo ./deploy/uninstall.sh --purge    ALSO delete resident state (destructive!)
set -Eeuo pipefail

PURGE=0
[[ "${1:-}" == "--purge" ]] && PURGE=1

SOFTWARE_DIR="${SH_SOFTWARE_DIR:-/opt/safe-harbor/software}"
CONFIG_DIR="${SH_CONFIG_DIR:-/etc/safe-harbor}"
STATE_DIR="${SH_STATE_DIR:-/var/lib/safe-harbor}"
BACKUP_DIR="${SH_BACKUP_DIR:-${STATE_DIR}/backups}"

if [[ "${EUID}" -ne 0 ]]; then
    echo "ERROR: uninstall must run as root" >&2
    exit 1
fi

echo "Safe Harbor uninstall"
echo "  resident state will be ${PURGE:-kept}"

# 1. Stop + disable services.
for unit in restate jnaapakam hermes-manager; do
    if systemctl list-unit-files "${unit}.service" >/dev/null 2>&1; then
        systemctl disable --now "${unit}.service" 2>/dev/null || true
        rm -f "/etc/systemd/system/${unit}.service"
        echo "removed unit: ${unit}.service"
    fi
done
systemctl daemon-reload

# 2. Remove the CLI.
rm -f /usr/local/bin/safeharbor

# 3. Remove software (reproducible — safe to delete).
if [[ -d "${SOFTWARE_DIR}" ]]; then
    rm -rf "${SOFTWARE_DIR}"
    echo "removed software: ${SOFTWARE_DIR}"
fi

# 4. Preserve config? No — config is regenerable templates + generated
#    secrets. Back it up first, then remove.
if [[ -d "${CONFIG_DIR}" ]]; then
    CONF_BACKUP="/root/safe-harbor-config-backup-$(date -u +%Y%m%dT%H%M%SZ)"
    cp -a "${CONFIG_DIR}" "${CONF_BACKUP}"
    rm -rf "${CONFIG_DIR}"
    echo "config backed up to ${CONF_BACKUP} and removed"
fi

if [[ "${PURGE}" == "1" ]]; then
    echo
    echo "DESTRUCTIVE: purging persistent resident state."
    read -r -p "Type PURGE to confirm deletion of ${STATE_DIR}: " answer
    if [[ "${answer}" != "PURGE" ]]; then
        echo "aborted — resident state was NOT deleted."
        exit 1
    fi
    rm -rf "${STATE_DIR}"
    echo "resident state purged: ${STATE_DIR}"
else
    echo
    echo "Resident state KEPT at ${STATE_DIR} (backups at ${BACKUP_DIR})."
    echo "To delete it deliberately: sudo ./deploy/uninstall.sh --purge"
fi

echo "uninstall complete."