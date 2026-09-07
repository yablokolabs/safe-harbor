#!/usr/bin/env bash
# Safe Harbor Gen1 — offline installer for the Ubuntu manager.
#
#   sudo ./deploy/install.sh                 real run (from the bundle)
#   sudo ./deploy/install.sh --dry-run       inspect without changing anything
#   sudo ./deploy/install.sh --bundle-dir X  where artifacts/ lives (default: next to this checkout)
#
# Principles:
#   * deterministic, idempotent, fail-fast
#   * artifacts must ALREADY be present and verified — never downloaded here
#   * reruns never corrupt completed work (explicit step state)
#   * resident state is never touched or deleted by this installer
#
# Components whose offline installation cannot be fully executed yet (they
# need the future Ubuntu integration environment) are recorded as
# REQUIRES_INTEGRATION_TEST instead of being silently marked healthy.
set -Eeuo pipefail

DRY=0
BUNDLE_DIR=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run) DRY=1 ;;
        --bundle-dir) BUNDLE_DIR="$2"; shift ;;
        *) echo "unknown option: $1" >&2; exit 2 ;;
    esac
    shift
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

SOFTWARE_DIR="${SH_SOFTWARE_DIR:-/opt/safe-harbor/software}"
CONFIG_DIR="${SH_CONFIG_DIR:-/etc/safe-harbor}"
STATE_DIR="${SH_STATE_DIR:-/var/lib/safe-harbor}"
# bootstrap.sh derives LOG_DIR/BACKUP_DIR and the service account from the
# same SH_* environment, so the paths always match the layout it creates.

# Where verified artifacts live: explicit --bundle-dir, else the extracted
# bundle layout (artifacts/ NEXT TO the safe-harbor/ checkout), else a dev
# checkout (artifacts/ inside it).
if [[ -n "${BUNDLE_DIR}" ]]; then
    ARTIFACTS_DIR="${BUNDLE_DIR}"
elif [[ -d "${ROOT_DIR}/artifacts" ]]; then
    ARTIFACTS_DIR="${ROOT_DIR}/artifacts"
elif [[ -d "${ROOT_DIR}/../artifacts" ]]; then
    ARTIFACTS_DIR="${ROOT_DIR}/../artifacts"
else
    ARTIFACTS_DIR="${ROOT_DIR}/artifacts"
fi
CHECKSUMS="${ROOT_DIR}/manifest/checksums.sha256"
STEP_FILE="${STATE_DIR}/install.steps"

say()  { echo "== $*"; }
step_done() { grep -qx "done:$1" "${STEP_FILE}" 2>/dev/null; }
mark_step() { echo "done:$1" >> "${STEP_FILE}"; }

# --- guards ---------------------------------------------------------------
if [[ "${DRY}" == "1" ]]; then
    echo "Safe Harbor install DRY-RUN — no changes will be made."
    echo "  software: ${SOFTWARE_DIR}"
    echo "  config:   ${CONFIG_DIR}"
    echo "  state:    ${STATE_DIR}"
    echo "  artifacts: ${ARTIFACTS_DIR}"
    echo
fi

if [[ "${DRY}" != "1" ]]; then
    if [[ "${EUID}" -ne 0 ]]; then
        echo "ERROR: install must run as root (sudo ./deploy/install.sh)" >&2
        exit 1
    fi
    # Gen1 target is Ubuntu. Refuse to modify anything else — including the
    # Debian build machine.
    if [[ -r /etc/os-release ]]; then
        # shellcheck disable=SC1091
        source /etc/os-release
        if [[ "${ID:-}" != "ubuntu" ]]; then
            echo "ERROR: install targets Ubuntu; this host is ${ID:-unknown} ${VERSION_ID:-}. " >&2
            echo "       Use ./deploy/preflight.sh on the target, and the bundle on the target." >&2
            exit 1
        fi
    fi
fi

if [[ ! -d "${ARTIFACTS_DIR}" ]]; then
    if [[ "${DRY}" == "1" ]]; then
        echo "NOTE: no verified artifacts at ${ARTIFACTS_DIR} (dry-run continues to print the plan)"
    else
        echo "ERROR: no verified artifacts at ${ARTIFACTS_DIR} — transfer the offline bundle first" >&2
        exit 1
    fi
fi

# --- artifact verification -------------------------------------------------
if [[ "${DRY}" != "1" ]]; then
    say "verifying offline artifacts"
    if ! (cd "${ARTIFACTS_DIR}" && sha256sum -c "${CHECKSUMS}"); then
        echo "ERROR: artifact verification FAILED — refusing to install" >&2
        exit 1
    fi
    echo "all artifacts verified against manifest/checksums.sha256"
fi

# --- step: layout + service account ----------------------------------------
if [[ "${DRY}" == "1" ]]; then
    say "would run deploy/bootstrap.sh"
else
    say "bootstrap (layout + service account)"
    if ! step_done bootstrap; then
        "${SCRIPT_DIR}/bootstrap.sh"
        mark_step bootstrap
    fi
fi

# --- step: safeharbor CLI ---------------------------------------------------
if [[ "${DRY}" == "1" ]]; then
    say "would install safeharbor CLI to /usr/local/bin/safeharbor"
else
    say "install safeharbor CLI"
    if ! step_done cli; then
        if python3 -m pip install --no-index --no-build-isolation "${ROOT_DIR}" >/dev/null 2>&1; then
            echo "CLI installed via pip (offline)"
        else
            install -m 0755 /dev/null /usr/local/bin/safeharbor
            cat > /usr/local/bin/safeharbor <<EOF
#!/usr/bin/env bash
exec python3 "${ROOT_DIR}/safeharbor/cli.py" "\$@"
EOF
            echo "CLI installed via launcher script"
        fi
        mark_step cli
    fi
fi

# --- step: restate -----------------------------------------------------------
if [[ "${DRY}" == "1" ]]; then
    say "would install Restate v1.7.2 from verified artifact"
else
    say "install Restate v1.7.2"
    if ! step_done restate; then
        TARBALL="${ARTIFACTS_DIR}/restate/restate-server-x86_64-unknown-linux-musl.tar.xz"
        mkdir -p "${SOFTWARE_DIR}/restate"
        tar -xJf "${TARBALL}" -C "${SOFTWARE_DIR}/restate" --strip-components=1
        chmod 0755 "${SOFTWARE_DIR}/restate/restate-server"
        chown -R root:root "${SOFTWARE_DIR}/restate"
        echo "restate-server installed: $("${SOFTWARE_DIR}/restate/restate-server" --version)"
        mark_step restate
    fi
fi

# --- step: uv ----------------------------------------------------------------
if [[ "${DRY}" == "1" ]]; then
    say "would install uv 0.12.10 from verified artifact"
else
    say "install uv"
    if ! step_done uv; then
        TARBALL="${ARTIFACTS_DIR}/uv/uv-x86_64-unknown-linux-gnu.tar.gz"
        mkdir -p "${SOFTWARE_DIR}/bin"
        tar -xzf "${TARBALL}" -C "${SOFTWARE_DIR}/bin" --strip-components=1
        chmod 0755 "${SOFTWARE_DIR}/bin/uv" "${SOFTWARE_DIR}/bin/uvx"
        chown -R root:root "${SOFTWARE_DIR}/bin"
        echo "uv installed: $("${SOFTWARE_DIR}/bin/uv" --version)"
        mark_step uv
    fi
fi

# --- step: jnaapakam ----------------------------------------------------------
# Offline install from vendored wheels when the bundle carries a wheelhouse;
# otherwise recorded as REQUIRES_INTEGRATION_TEST (never faked).
if [[ "${DRY}" == "1" ]]; then
    say "would install jnaapakam 0.5.1 (offline wheelhouse or REQUIRES_INTEGRATION_TEST)"
else
    say "install jnaapakam"
    if ! step_done jnaapakam; then
        WHEEL_TARBALL="${ARTIFACTS_DIR}/python-wheels/jnaapakam-wheels-cp313-amd64.tar.gz"
        if [[ -f "${WHEEL_TARBALL}" ]]; then
            WHEEL_DIR="${SOFTWARE_DIR}/jnaapakam/wheels"
            mkdir -p "${WHEEL_DIR}"
            tar -xzf "${WHEEL_TARBALL}" -C "${WHEEL_DIR}"
            python3 -m venv "${SOFTWARE_DIR}/jnaapakam/venv"
            "${SOFTWARE_DIR}/jnaapakam/venv/bin/pip" install --no-index \
                --find-links "${WHEEL_DIR}" "jnaapakam==0.5.1"
            chown -R root:root "${SOFTWARE_DIR}/jnaapakam"
            echo "jnaapakam installed from vendored wheelhouse"
        else
            echo "no offline wheelhouse in bundle — jnaapakam install: REQUIRES_INTEGRATION_TEST"
            echo "  (re-run acquisition with a python wheelhouse, or install on the target with network)"
        fi
        mark_step jnaapakam
    fi
fi

# --- step: hermes ---------------------------------------------------------------
if [[ "${DRY}" == "1" ]]; then
    say "would vendor Hermes Agent v0.21.0 source (offline env: REQUIRES_INTEGRATION_TEST)"
else
    say "vendor Hermes Agent v0.21.0"
    if ! step_done hermes; then
        TARBALL="${ARTIFACTS_DIR}/hermes/hermes-agent-v2026.8.31.tar.gz"
        mkdir -p "${SOFTWARE_DIR}/hermes"
        tar -xzf "${TARBALL}" -C "${SOFTWARE_DIR}/hermes" --strip-components=1
        chown -R root:root "${SOFTWARE_DIR}/hermes"
        echo "hermes source vendored to ${SOFTWARE_DIR}/hermes"
        echo "NOTE: Hermes' Python environment cannot be constructed fully offline in Gen1"
        echo "      without a complete wheelhouse — REQUIRES_INTEGRATION_TEST"
        mark_step hermes
    fi
fi

# --- step: configuration --------------------------------------------------------
if [[ "${DRY}" == "1" ]]; then
    say "would install configuration templates to ${CONFIG_DIR}"
else
    say "install configuration (never overwrites existing config)"
    if ! step_done config; then
        if [[ -d "${ROOT_DIR}/config" ]]; then
            mkdir -p "${CONFIG_DIR}"
            # copy templates only where no file exists yet
            (cd "${ROOT_DIR}/config" && find . -type f | while read -r f; do
                target="${CONFIG_DIR}/${f#./}"
                if [[ ! -e "${target}" ]]; then
                    mkdir -p "$(dirname "${target}")"
                    cp "${f}" "${target}"
                    echo "config: ${target}"
                fi
            done)
            # generate secrets (never committed, never in units)
            if [[ ! -f "${CONFIG_DIR}/.env" ]] && [[ -f "${CONFIG_DIR}/.env.example" ]]; then
                sed "s/__RANDOM_HEX__/$(openssl rand -hex 32)/g" \
                    "${CONFIG_DIR}/.env.example" > "${CONFIG_DIR}/.env"
                chmod 0600 "${CONFIG_DIR}/.env"
                echo "generated ${CONFIG_DIR}/.env (secrets, mode 0600)"
            fi
        fi
        mark_step config
    fi
fi

# --- step: systemd --------------------------------------------------------------
if [[ "${DRY}" == "1" ]]; then
    say "would install systemd units: restate.service, jnaapakam.service, hermes-manager.service"
else
    say "install systemd units"
    if ! step_done systemd; then
        for unit in restate jnaapakam hermes-manager; do
            src="${ROOT_DIR}/systemd/${unit}.service"
            if [[ -f "${src}" ]]; then
                install -m 0644 "${src}" "/etc/systemd/system/${unit}.service"
                echo "unit: ${unit}.service"
            fi
        done
        systemctl daemon-reload
        mark_step systemd
    fi
fi

# --- step: services ----------------------------------------------------------------
if [[ "${DRY}" == "1" ]]; then
    say "would enable + start: restate, jnaapakam (hermes-manager requires integration config)"
else
    say "enable + start services"
    if ! step_done services; then
        for unit in restate jnaapakam; do
            systemctl enable "${unit}.service" >/dev/null 2>&1 || true
            systemctl restart "${unit}.service" || echo "WARN: ${unit}.service failed to start — check journalctl -u ${unit}"
        done
        systemctl enable hermes-manager.service >/dev/null 2>&1 || true
        echo "hermes-manager.service enabled but not started (requires a configured Hermes install — REQUIRES_INTEGRATION_TEST)"
        mark_step services
    fi
fi

# --- step: generation manifest + doctor --------------------------------------------
if [[ "${DRY}" != "1" ]] && command -v safeharbor >/dev/null 2>&1; then
    say "record generation manifest + doctor"
    safeharbor generation record >/dev/null 2>&1 || true
    safeharbor doctor || true
fi

echo
echo "install complete. Next steps:"
echo "  safeharbor doctor"
echo "  safeharbor status"
echo "  See runbooks/DEPLOYMENT.md and runbooks/OFFLINE_INSTALL.md"