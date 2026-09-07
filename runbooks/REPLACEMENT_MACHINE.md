# Runbook: Replacement Machine

Recovery must NOT assume the original Manager OS remains accessible.

```
Manager A  --X destroyed/unavailable

Replacement Manager B
   Clean Ubuntu 26.04.1 LTS
   -> Verified Safe Harbor bundle
   -> Recreate software environment
   -> Restore resident state
   -> Validate continuity
   -> Reconnect Specialist
   -> Resume
```

## Prerequisites on the surviving side

- The offline bundle (`safe-harbor-gen1-0.1.0-amd64.tar.gz` + `.sha256`),
  or the acquisition machine to rebuild it.
- The most recent validated backup
  (`/var/lib/safe-harbor/backups/backup-<ID>/`) — copied off the old
  machine BEFORE it was lost, or from the Specialist/offline storage.
- The Specialist node, which holds no manager state and needs no changes.

## Procedure

### 1. Fresh OS, verify bundle

```bash
sha256sum -c safe-harbor-gen1-0.1.0-amd64.tar.gz.sha256
tar -xzf safe-harbor-gen1-0.1.0-amd64.tar.gz
cd safe-harbor-gen1-0.1.0-amd64
```

### 2. Preflight + bootstrap + install

```bash
sudo ./safe-harbor/deploy/preflight.sh
sudo ./safe-harbor/deploy/bootstrap.sh
sudo ./safe-harbor/deploy/install.sh
```

This recreates the **software environment** — reproducible from verified
artifacts, byte-for-byte the same generation as Manager A.

### 3. Restore resident state from the validated backup

```bash
sudo safeharbor restore --dry-run /path/to/backup-<ID>
sudo safeharbor restore /path/to/backup-<ID>
```

The backup is fully self-describing: manifest + per-file SHA-256, with the
generation snapshot embedded. A corrupt or incomplete backup is refused.

### 4. Validate continuity

```bash
safeharbor doctor
safeharbor validate --backup /path/to/backup-<ID>
```

Check the jñāpakaṁ identity is unchanged (it is portable, not derived
from the machine):

```bash
curl -s http://127.0.0.1:8889/agent
```

The `urn:jnaapakam:agent:*` URN on the replacement MUST equal the URN
from Manager A. That is the continuity test. Hostname, MAC, disk UUID,
CPU and serial are environment metadata — they are expected to change.

### 5. Reconnect the Specialist

- The Specialist's A2A config is unchanged (it dials the manager by the
  address in `/etc/safe-harbor/a2a/peers.json`).
- Update the manager's `peers.json` if the Specialist address or token
  changed. Tokens are in environment variables, never in the backup.
- Verify: `safeharbor a2a-test` (levels 1-6).

### 6. Resume

```bash
safeharbor status
safeharbor backup --note "post-replacement recovery point"
```

Record the reconstruction as a new generation manifest entry (restore
does this automatically).

## What does NOT carry over (by design)

- `hostname`, MAC, disk UUID, CPU, serial, model, GPU — environment
  metadata, never resident identity.
- `/etc/safe-harbor/.env` secrets — regenerated on install.
- Nothing in `/opt/safe-harbor/software/` — reproduced from the bundle.

## Honest status

Steps 1-4 are fully scripted and locally tested. Step 5 requires the real
Windows Specialist → `REQUIRES_A2A_INTEGRATION_TEST`.