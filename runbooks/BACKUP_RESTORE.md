# Runbook: Backup and Restore

## Backup

```bash
sudo safeharbor backup
```

Or via the operator wrapper (cron-safe):

```bash
sudo ./scripts/backup.sh --note "weekly recovery point"
```

### What a backup contains

| Source | Strategy | Why this is consistent |
|--------|----------|------------------------|
| Restate data dir | quiesced copy (service stopped while copying) | copying a live Restate data dir is NOT a consistent backup |
| jñāpakaṁ store | official `GET /backup` JSON export when the server is up; else quiesced copy of `memory.db` | the API export is the upstream-supported mechanism |
| jñāpakaṁ soul files | plain copy from `resident/` | resident identity, always captured |
| Hermes `HERMES_HOME` | quiesced copy (gateway stopped while copying) | live tree copy is not consistent |
| project state | plain copy | files are self-consistent |
| generation manifest | snapshot | environment metadata |
| reconstruction config | copy of `/etc/safe-harbor` (secrets excluded) | a replacement machine can reconstruct |
| backup manifest | generated JSON + per-file SHA-256 | the integrity record |

Backups land in `/var/lib/safe-harbor/backups/backup-<UTC-timestamp>/`.
Every staged file is hashed (SHA-256) and listed in
`backup-manifest.json` before the backup is published atomically — a
failed run never corrupts the previous backup.

Inspect a backup without Safe Harbor:

```bash
cat /var/lib/safe-harbor/backups/backup-*/backup-manifest.json
sha256sum -c /var/lib/safe-harbor/backups/backup-*/backup-manifest.json  # no: hashes live INSIDE the manifest
# verify contents with:
safeharbor validate --backup /var/lib/safe-harbor/backups/backup-*
```

## Restore

Restore is destructive by nature. It requires: a readable, schema-compatible
manifest; every listed file present with a matching SHA-256; no silently
newer resident state; and explicit operator confirmation.

```bash
# 1. inspect + validate, change nothing
sudo safeharbor restore --dry-run /var/lib/safe-harbor/backups/backup-<ID>

# 2. deliberate restore (asks for YES)
sudo safeharbor restore /var/lib/safe-harbor/backups/backup-<ID>
```

Or via the operator wrapper (always dry-runs first):

```bash
sudo ./scripts/restore.sh /var/lib/safe-harbor/backups/backup-<ID>
```

### Refusals (by design)

- corrupt/incomplete backup → refused (missing file or hash mismatch)
- newer resident state recorded than the backup → refused unless `--force`
- unsupported manifest schema → refused

After restore, `safeharbor doctor` validates continuity. The restoration
is recorded as a new generation manifest entry.

## Consistency notes

- Never `tar` a live Restate data directory and call it a backup.
- Never copy `HERMES_HOME` while the gateway is running and call it a backup.
- jñāpakaṁ export/restore is the upstream API path; file placement is the
  deterministic offline path. Both are implemented; the API path needs a
  live server (REQUIRES_INTEGRATION_TEST on the real pair).

## Retention

Gen1 has no retention policy engine. Suggested minimum (documented, not
automated): one backup before any configuration change, one after each
successful reconstruction, and at least weekly during operation. Old
backups are plain directories — archive them with your normal tooling.