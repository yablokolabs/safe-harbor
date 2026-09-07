# Runbook: Deployment (Gen1 Manager)

Target: **Ubuntu Server 26.04.1 LTS, amd64, UEFI, systemd, CPU-only**.
Minimum hardware: 4 cores / 8 GiB RAM / 128 GiB disk.
Secure Boot may remain enabled. No GPU required. Ethernet or Wi-Fi 5+.

This runbook assumes the offline bundle has been physically transferred.
For bundle creation/verification, see `OFFLINE_INSTALL.md`.

## 0. Preconditions

- Clean Ubuntu Server 26.04.1 LTS installation, updated if a mirror is available.
- Operator account with `sudo`.
- The offline bundle plus its `.sha256` file present on the machine.

## 1. Verify the bundle (offline, no network involved)

```bash
sha256sum -c safe-harbor-gen1-0.1.0-amd64.tar.gz.sha256
tar -xzf safe-harbor-gen1-0.1.0-amd64.tar.gz
cd safe-harbor-gen1-0.1.0-amd64
```

## 2. Preflight

```bash
sudo ./safe-harbor/deploy/preflight.sh
```

Every check must be PASS or WARN. Any FAIL blocks installation.
`preflight.sh` is a checker only — it changes nothing.

Known honest results on non-target hosts:
- on the Debian build machine, `distribution` reports WARN ("not the Ubuntu Gen1 target").

## 3. Bootstrap (layout + dedicated service account)

```bash
sudo ./safe-harbor/deploy/bootstrap.sh
```

Creates:

| Path | Purpose |
|------|---------|
| `/opt/safe-harbor/software/` | reproducible software (deletable) |
| `/etc/safe-harbor/` | configuration |
| `/var/lib/safe-harbor/resident/` | resident identity (SOUL/IDENTITY/MEMORY) |
| `/var/lib/safe-harbor/hermes/` | Hermes agent data (`HERMES_HOME`) |
| `/var/lib/safe-harbor/jnaapakam/` | jñāpakaṁ store |
| `/var/lib/safe-harbor/restate/` | Restate durable state |
| `/var/lib/safe-harbor/projects/` | project state |
| `/var/lib/safe-harbor/generations/` | generation manifests |
| `/var/lib/safe-harbor/backups/` | completed backups |
| `/var/log/safe-harbor/` | logs |

The `safeharbor` system user owns only its persistent-state directories
(least privilege). Software and config stay root-owned.

## 4. Install (verified artifacts only — never downloads)

```bash
sudo ./safe-harbor/deploy/install.sh
```

Idempotent: completed steps are recorded in
`/var/lib/safe-harbor/install.steps`; a rerun after partial failure skips
completed work and never corrupts it. Artifact hashes are re-verified
against `manifest/checksums.sha256` before anything is installed.

Status of each component after a Gen1 bundle install:

| Component | Gen1 bundle status |
|-----------|--------------------|
| Restate v1.7.2 | installed from verified binary, service started |
| uv 0.12.10 | installed (offline Python tooling) |
| jñāpakaṁ 0.5.1 | installed **iff** the bundle carries a wheelhouse; else REQUIRES_INTEGRATION_TEST |
| Hermes v0.21.0 | source vendored; offline env REQUIRES_INTEGRATION_TEST |

## 5. Configure

- A2A peers: edit `/etc/safe-harbor/a2a/peers.json` (see `config/a2a/README.md`).
- Credentials: `/etc/safe-harbor/.env` is generated with fresh secrets
  (mode 0600). Never commit it.
- Hermes/jñāpakaṁ/Restate environment files:
  `/etc/safe-harbor/{hermes,jnaapakam,restate}/environment`.

## 6. Firewall (explicit, documented rules only)

Gen1 listeners and their intended exposure:

| Port | Service | Exposure |
|------|---------|----------|
| 8080 | Restate ingress | loopback only (deny on LAN) |
| 9070 | Restate admin | loopback only (deny on LAN) |
| 8889 | jñāpakaṁ | loopback only (deny on LAN) |
| 9900 | Hermes A2A | private LAN, authenticated peers only |

With `ufw`:

```bash
sudo ufw default deny incoming
sudo ufw allow from <SPECIALIST_LAN_IP> to any port 9900 proto tcp comment 'safeharbor a2a'
sudo ufw allow from <MANAGER_LAN_IP>   to any port 9900 proto tcp comment 'safeharbor a2a'
sudo ufw deny 9900/tcp
sudo ufw deny 8080/tcp
sudo ufw deny 9070/tcp
sudo ufw deny 8889/tcp
sudo ufw enable
```

Restate has no bind-address config key (verified via `--dump-config`), so
loopback restriction for 8080/9070 is enforced here, at the firewall —
not silently in software.

## 7. Start + validate

```bash
systemctl enable --now restate jnaapakam
safeharbor doctor
```

Services and logs:

```bash
systemctl status restate jnaapakam hermes-manager
journalctl -u restate -n 50
journalctl -u jnaapakam -n 50
```

`hermes-manager.service` is installed and enabled but intentionally not
started until the Hermes environment is constructed on the target
(REQUIRES_INTEGRATION_TEST).

## 8. Record the generation manifest

```bash
safeharbor generation record
safeharbor generation show
```

The generation manifest records component pins and OS metadata. It never
binds resident identity to hostname, MAC, disk UUID, CPU or serial.

## 9. First continuity check

```bash
safeharbor status
safeharbor backup          # create the first recovery point
safeharbor validate --backup /var/lib/safe-harbor/backups/backup-*
```

Never move on to operating the agent until the first backup validates.