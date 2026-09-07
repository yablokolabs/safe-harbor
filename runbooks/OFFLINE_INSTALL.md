# Runbook: Offline-First Acquisition and Installation

Runtime operation must not depend on Internet access. There are two
stages. Stage A runs on the **connected acquisition machine** (the Debian
build host). Stage B runs on the **air-gapped Ubuntu target**.

## Stage A — connected acquisition machine

Everything is driven by the lock manifest
`manifest/artifacts.lock` — the single source of truth for component,
version, source, architecture, URL and SHA-256. `acquire.sh` never
decides anything itself.

```bash
# 1. read lock manifest, acquire exact artifacts, verify hashes
./acquisition/acquire.sh

# 2. re-verify what is cached (also safe on the target)
./acquisition/verify.sh

# 3. assemble the offline bundle + hash it
./acquisition/assemble.sh        # or: make bundle
```

Output:

```
dist/safe-harbor-gen1-0.1.0-amd64.tar.gz
dist/safe-harbor-gen1-0.1.0-amd64.tar.gz.sha256
```

The bundle contains:

- the Safe Harbor repository (CLI, deploy scripts, systemd units, runbooks, tests)
- `artifacts/` — every locked upstream artifact (Restate binary, Hermes
  source, jñāpakaṁ source, uv), each verified
- `manifest/` — versions.lock, artifacts.lock, checksums.sha256

Verification status per artifact (from `manifest/artifacts.lock`):

| Artifact | SHA-256 | Status |
|----------|---------|--------|
| restate-server v1.7.2 musl amd64 | `d702d2db…` | verified against upstream `sha256.sum` |
| hermes-agent v2026.8.31 source | `78fb3ff7…` | hash recorded (no upstream per-artifact checksum; tag pinned) |
| jnaapakam 0.5.1 @ 7fa08bb source | `8b751cf2…` | hash recorded (commit pinned) |
| uv 0.12.10 amd64 | `173d95a0…` | verified against upstream `.sha256` |

## Physical transfer

Copy the bundle + its `.sha256` to the target (USB, verified LAN, …).
Transit integrity is checked on the target with `sha256sum -c`.

## Stage B — air-gapped target

```bash
sha256sum -c safe-harbor-gen1-0.1.0-amd64.tar.gz.sha256   # verify bundle
tar -xzf safe-harbor-gen1-0.1.0-amd64.tar.gz
cd safe-harbor-gen1-0.1.0-amd64

sudo ./safe-harbor/deploy/preflight.sh
sudo ./safe-harbor/deploy/bootstrap.sh
sudo ./safe-harbor/deploy/install.sh
safeharbor doctor
```

**The installer never reaches the Internet.** If an artifact is missing or
its hash fails, installation FAILS — it does not download anything.

## Known offline gaps (honest status)

| Capability | Status |
|------------|--------|
| Restate binary install | TESTED (verified artifact, unit installed) |
| jñāpakaṁ install | REQUIRES_INTEGRATION_TEST unless the bundle carries `artifacts/python-wheels/` |
| Hermes Python environment | REQUIRES_INTEGRATION_TEST (full wheelhouse not vendored in Gen1) |
| CLI, systemd, config | TESTED LOCALLY |

`REQUIRES_INTEGRATION_TEST` items are never reported as healthy; `safeharbor
doctor` shows them as `NOT_CONFIGURED` / `REQUIRES_TEST`.