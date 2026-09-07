#!/usr/bin/env bash
# Safe Harbor Gen1 — preflight validation.
#
# Runs BEFORE anything is changed on the target. Reports each check as
# PASS / FAIL / WARN / SKIP and exits 1 if any FAIL is present.
#
# This script is a CHECKER ONLY: it never modifies the machine. It is safe
# to run on any Linux host (including the Debian build machine), where it
# will honestly report that the Ubuntu target checks do not apply.
set -Eeuo pipefail

PASS=0
FAIL=0
WARN=0

report() {
    local state="$1" label="$2" detail="$3"
    case "${state}" in
        PASS) PASS=$((PASS + 1)) ;;
        FAIL) FAIL=$((FAIL + 1)) ;;
        WARN) WARN=$((WARN + 1)) ;;
    esac
    printf "%-5s %-24s %s\n" "${state}" "${label}" "${detail}"
}

fail()  { report FAIL "$1" "$2"; }
pass()  { report PASS "$1" "$2"; }
warn()  { report WARN "$1" "$2"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

echo "Safe Harbor Gen1 preflight — $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo

# --- distribution ---------------------------------------------------------
DISTRO_ID="unknown"
DISTRO_VERSION="unknown"
if [[ -r /etc/os-release ]]; then
    # shellcheck disable=SC1091
    source /etc/os-release
    DISTRO_ID="${ID:-unknown}"
    DISTRO_VERSION="${VERSION_ID:-unknown}"
fi

case "${DISTRO_ID}" in
    ubuntu)
        if [[ "${DISTRO_VERSION}" == 26.04* ]]; then
            pass "distribution" "Ubuntu ${DISTRO_VERSION} LTS (supported)"
        else
            fail "distribution" "Ubuntu ${DISTRO_VERSION} — Gen1 supports 26.04 LTS"
        fi
        ;;
    debian)
        warn "distribution" "Debian ${DISTRO_VERSION} — build/acquisition machine, NOT the Ubuntu Gen1 target"
        ;;
    *)
        fail "distribution" "unsupported OS: ${DISTRO_ID} ${DISTRO_VERSION}"
        ;;
esac

# --- architecture ---------------------------------------------------------
case "$(uname -m)" in
    x86_64|amd64) pass "architecture" "amd64 / x86_64 (supported)" ;;
    *) fail "architecture" "$(uname -m) — Gen1 targets amd64" ;;
esac

# --- systemd --------------------------------------------------------------
if [[ "$(ps -p 1 -o comm= 2>/dev/null || echo unknown)" == "systemd" ]] && command -v systemctl >/dev/null 2>&1; then
    pass "systemd" "PID 1 is systemd"
else
    fail "systemd" "systemd is required (PID 1 is $(ps -p 1 -o comm= 2>/dev/null || echo '?'))"
fi

# --- UEFI -----------------------------------------------------------------
if [[ -d /sys/firmware/efi ]]; then
    pass "uefi" "UEFI firmware detected"
else
    warn "uefi" "no UEFI runtime detected (BIOS/legacy boot — works, but Gen1 is validated on UEFI)"
fi

# --- hardware -------------------------------------------------------------
CORES=$(nproc 2>/dev/null || echo 0)
if [[ "${CORES}" -ge 8 ]]; then
    pass "cpu" "${CORES} cores (preferred)"
elif [[ "${CORES}" -ge 4 ]]; then
    pass "cpu" "${CORES} cores (minimum)"
else
    fail "cpu" "${CORES} cores — Gen1 minimum is 4"
fi

RAM_MB=0
if [[ -r /proc/meminfo ]]; then
    RAM_MB=$(( $(awk '/MemTotal/ {print $2}' /proc/meminfo) / 1024 ))
fi
if [[ "${RAM_MB}" -ge 16384 ]]; then
    pass "ram" "${RAM_MB} MiB (preferred)"
elif [[ "${RAM_MB}" -ge 8192 ]]; then
    pass "ram" "${RAM_MB} MiB (minimum)"
else
    fail "ram" "${RAM_MB} MiB — Gen1 minimum is 8192 MiB"
fi

DISK_GB=0
if command -v df >/dev/null 2>&1; then
    DISK_GB=$(df -Pk /var/lib 2>/dev/null | awk 'NR==2 {printf "%.0f", $2/1024/1024}')
fi
if [[ "${DISK_GB}" -ge 256 ]]; then
    pass "disk" "${DISK_GB} GiB (preferred)"
elif [[ "${DISK_GB}" -ge 128 ]]; then
    pass "disk" "${DISK_GB} GiB (minimum)"
else
    fail "disk" "${DISK_GB} GiB — Gen1 minimum is 128 GiB"
fi

# --- network --------------------------------------------------------------
IFACES=""
for iface in /sys/class/net/*; do
    name="${iface##*/}"
    if [[ "${name}" != "lo" ]] && [[ -d "${iface}" ]]; then
        IFACES="${IFACES}${IFACES:+ }${name}"
    fi
done
if [[ -n "${IFACES}" ]]; then
    pass "network" "interfaces: ${IFACES}"
else
    fail "network" "no non-loopback network interface found"
fi

# --- required ports -------------------------------------------------------
# Safe Harbor Gen1 listeners (all loopback-bound on the manager):
#   jnaapakam 8889, restate admin 9070 + ingress 8080, hermes A2A 9900.
for port in 8080 8889 9070 9900; do
    if ss -ltn 2>/dev/null | grep -q "[:.]${port}[[:space:]]"; then
        warn "port-${port}" "already in use on this host (will conflict if the component binds it)"
    else
        pass "port-${port}" "free"
    fi
done

# --- time sanity ----------------------------------------------------------
EPOCH=$(date +%s 2>/dev/null || echo 0)
if [[ "${EPOCH}" -gt 1600000000 ]] && [[ "${EPOCH}" -lt 4102444800 ]]; then
    pass "time" "system clock sane ($(date -u +%Y-%m-%d))"
else
    fail "time" "system clock is not sane (epoch ${EPOCH})"
fi

# --- offline artifacts ----------------------------------------------------
# In the extracted bundle, artifacts/ sits NEXT TO the safe-harbor/ checkout
# (bundle root); in a dev checkout it sits inside it. Check both.
if [[ -d "${ROOT_DIR}/artifacts" ]]; then
    ARTIFACTS_DIR="${ROOT_DIR}/artifacts"
elif [[ -d "${ROOT_DIR}/../artifacts" ]]; then
    ARTIFACTS_DIR="${ROOT_DIR}/../artifacts"
else
    ARTIFACTS_DIR="${ROOT_DIR}/artifacts"
fi
CHECKSUMS="${ROOT_DIR}/manifest/checksums.sha256"
if [[ -d "${ARTIFACTS_DIR}" ]] && [[ -f "${CHECKSUMS}" ]]; then
    if (cd "${ARTIFACTS_DIR}" && sha256sum -c "${CHECKSUMS}" >/dev/null 2>&1); then
        pass "artifacts" "all offline artifacts present and hashes verified"
    else
        fail "artifacts" "artifact hashes do not match manifest/checksums.sha256"
    fi
else
    warn "artifacts" "no bundle artifacts next to this checkout (expected under artifacts/ inside an offline bundle)"
fi

echo
echo "preflight result: $(if [[ "${FAIL}" -gt 0 ]]; then echo FAIL; elif [[ "${WARN}" -gt 0 ]]; then echo "WARN (${WARN})"; else echo PASS; fi) — ${PASS} pass, ${FAIL} fail, ${WARN} warn"
if [[ "${FAIL}" -gt 0 ]]; then
    echo "preflight FAILED — do not install until the FAIL checks are resolved."
    exit 1
fi
exit 0