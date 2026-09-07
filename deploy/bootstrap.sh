#!/usr/bin/env bash
# Safe Harbor Gen1 — bootstrap.
#
# Creates the filesystem layout and the dedicated service account BEFORE
# the software installer runs. Idempotent; safe to rerun after partial
# failure. Never touches resident data.
#
#   sudo ./deploy/bootstrap.sh            real run
#   sudo ./deploy/bootstrap.sh --dry-run  show what would be done
set -Eeuo pipefail

DRY=0
[[ "${1:-}" == "--dry-run" ]] && DRY=1

SOFTWARE_DIR="${SH_SOFTWARE_DIR:-/opt/safe-harbor/software}"
CONFIG_DIR="${SH_CONFIG_DIR:-/etc/safe-harbor}"
STATE_DIR="${SH_STATE_DIR:-/var/lib/safe-harbor}"
LOG_DIR="${SH_LOG_DIR:-/var/log/safe-harbor}"
BACKUP_DIR="${SH_BACKUP_DIR:-${STATE_DIR}/backups}"
SERVICE_USER="safeharbor"
SERVICE_GROUP="safeharbor"

if [[ "${DRY}" == "1" ]]; then
    echo "[dry-run] would create:"
    echo "  software  ${SOFTWARE_DIR}"
    echo "  config    ${CONFIG_DIR}"
    echo "  state     ${STATE_DIR}"
    echo "  backups   ${BACKUP_DIR}"
    echo "  logs      ${LOG_DIR}"
    echo "  user/group ${SERVICE_USER}"
    exit 0
fi

if [[ "${EUID}" -ne 0 ]]; then
    echo "ERROR: bootstrap must run as root (sudo ./deploy/bootstrap.sh)" >&2
    exit 1
fi

# --- service account ------------------------------------------------------
if ! getent group "${SERVICE_GROUP}" >/dev/null 2>&1; then
    groupadd --system "${SERVICE_GROUP}"
    echo "created group ${SERVICE_GROUP}"
fi
if ! id "${SERVICE_USER}" >/dev/null 2>&1; then
    useradd --system --gid "${SERVICE_GROUP}" --home-dir "${STATE_DIR}" \
        --shell /usr/sbin/nologin "${SERVICE_USER}"
    echo "created user ${SERVICE_USER}"
fi

# --- directory tree (software vs persistent state kept strictly separate) --
mkdir -p "${SOFTWARE_DIR}" "${CONFIG_DIR}"
mkdir -p "${STATE_DIR}/resident" "${STATE_DIR}/hermes" "${STATE_DIR}/jnaapakam" \
         "${STATE_DIR}/restate" "${STATE_DIR}/projects" "${STATE_DIR}/generations"
mkdir -p "${BACKUP_DIR}" "${LOG_DIR}"
echo "created layout: software=${SOFTWARE_DIR} config=${CONFIG_DIR} state=${STATE_DIR}"

# --- ownership ------------------------------------------------------------
# Software and config are root-owned; the service user needs write access
# ONLY to its own persistent-state and log directories (least privilege).
chown -R "${SERVICE_USER}:${SERVICE_GROUP}" "${STATE_DIR}/resident" "${STATE_DIR}/hermes" \
         "${STATE_DIR}/jnaapakam" "${STATE_DIR}/restate" "${STATE_DIR}/projects" \
         "${STATE_DIR}/generations" "${BACKUP_DIR}" "${LOG_DIR}"
chmod 750 "${STATE_DIR}" "${STATE_DIR}/resident" "${STATE_DIR}/hermes" \
          "${STATE_DIR}/jnaapakam" "${STATE_DIR}/restate" "${STATE_DIR}/projects" \
          "${STATE_DIR}/generations" "${BACKUP_DIR}" "${LOG_DIR}"
echo "ownership + permissions set (least privilege)"

echo "bootstrap complete."
echo "next: sudo ./deploy/install.sh"