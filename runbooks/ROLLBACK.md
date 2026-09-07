# Runbook: Rollback

**Software rollback and resident-state rollback are DIFFERENT operations.**
They are never combined implicitly.

```
Software generation N          Resident state current
        |
        v
Software generation N-1        Resident state REMAINS current
```

## Software rollback

Software is reproducible from the verified bundle, so "rollback" is a
rebuild from the artifacts:

```bash
sudo ./scripts/rollback.sh software                 # rebuild from the current bundle
sudo ./scripts/rollback.sh software --bundle /path/to/safe-harbor-gen1-0.1.0-amd64
```

This reinstalls the pinned components. Resident state is untouched.

## Resident-state rollback

```bash
sudo ./scripts/rollback.sh state /var/lib/safe-harbor/backups/backup-<ID>
```

Equivalent to `scripts/restore.sh` — dry-run validation first, explicit
confirmation, refuses corrupt/incomplete backups and refuses to silently
overwrite newer state (unless `--force`).

## Before risky changes

Before an upgrade or configuration change, create or require a recovery
point:

```bash
sudo safeharbor backup --note "before <change description>"
```

After the change, `safeharbor validate` confirms the environment is still
coherent. If not, roll back software first (rebuild), then — only if the
change touched resident data — roll back state from the recovery point.

## Decision table

| Situation | Operation |
|-----------|-----------|
| Bad upgrade, state fine | `rollback.sh software` |
| Corrupt state, software fine | `rollback.sh state <backup>` |
| Both bad | software rollback FIRST, then state rollback — two explicit operations |
| Machine destroyed | runbooks/REPLACEMENT_MACHINE.md |