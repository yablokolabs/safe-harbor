# Safe Harbor

[![PyPI version](https://img.shields.io/pypi/v/safeharbor.svg?label=pypi)](https://pypi.org/project/safeharbor/)
[![Python](https://img.shields.io/pypi/pyversions/safeharbor.svg?cacheSeconds=86400)](https://pypi.org/project/safeharbor/)
[![CI](https://img.shields.io/github/actions/workflow/status/yablokolabs/safe-harbor/ci.yml?branch=main&label=CI)](https://github.com/yablokolabs/safe-harbor/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/actions/workflow/status/yablokolabs/safe-harbor/pypi.yml?label=release)](https://github.com/yablokolabs/safe-harbor/actions/workflows/pypi.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![GitHub](https://img.shields.io/badge/github-yablokolabs%2Fsafe--harbor-blue.svg)](https://github.com/yablokolabs/safe-harbor)

**Yabloko Labs** — open-source project for reproducible deployment, recovery,
validation and migration of persistent local AI agent environments.

> Safe Harbor makes the execution environment replaceable while preserving
> verifiable agent continuity.

Every compute node should be replaceable. Persistent state must be portable
independently of the machine executing it.

---

## 1. What is Safe Harbor?

Safe Harbor is a small, transparent toolchain that:

- reproducibly constructs a persistent local-agent environment;
- installs it **without Internet access** from a verified offline bundle;
- pins and verifies every software dependency;
- keeps **software/environment** strictly separate from **persistent agent state**;
- inspects system health (`safeharbor status` / `safeharbor doctor`);
- backs up persistent state consistently (quiesced, never a hot `tar` of live databases);
- validates backups before recovery;
- restores onto a clean replacement machine;
- reconnects specialist agent nodes;
- validates continuity after reconstruction;
- tests restart/reboot recovery;
- records environment/generation metadata;
- provides deterministic operational runbooks.

Safe Harbor itself must never become the permanent identity of an agent.
Models, runtimes, machines, OSes, inference engines and infrastructure
components remain replaceable.

## 2. What problem does it solve?

Persistent local agent environments die with their machines. A laptop dies,
a VM image corrupts, an OS upgrade breaks the runtime, and the agent's
accumulated identity, memory, durable workflows and project state are lost —
or worse, are only recoverable by copying a live machine, which is not a
consistent backup. Safe Harbor treats the machine as disposable and the
state as portable, so a replacement machine can be rebuilt reproducibly from
verified software artifacts plus validated persistent state.

## 3. What is Gen1?

Gen1 is the first supported reference architecture:

```
                    USER
                      │
                      ▼
              Agent Interface
                      │
                      ▼
┌────────────────────────────────────────┐
│          LINUX MANAGER NODE            │
│ Agent Runtime / Continuity / Memory    │
│ Durable Execution / Safe Harbor        │
│ Project State / Backup/Recovery/Validation
└───────────────────┬────────────────────┘
                    │ authenticated private-LAN A2A
                    ▼
┌────────────────────────────────────────┐
│          SPECIALIST NODE (Windows)     │
│ Agent Runtime / Local Models           │
│ Local Knowledge Sources / Approved     │
│ Local Tools / Approved Local Data      │
└────────────────────────────────────────┘
```

The Manager coordinates. The Specialist executes capabilities belonging to
its local environment. The Manager has **no** unrestricted remote shell,
PowerShell, filesystem or administrator access to the Specialist.

Gen1's one job:

> Prove that a persistent agent environment can survive process, software,
> OS and machine interruption, and be reconstructed reproducibly from
> verified software artifacts plus portable persistent state.

## 4. Supported platforms

| Role | Platform | Status |
|------|----------|--------|
| Manager (Gen1 target) | Ubuntu Server 26.04.1 LTS, amd64, UEFI, systemd, CPU-only | REQUIRES INTEGRATION |
| Build/acquisition machine | Debian GNU/Linux 13 (trixie), amd64 | TESTED (this repo was built here) |
| Specialist (initial) | Windows (native Hermes install) | REQUIRES INTEGRATION |

Minimum manager hardware: 4 cores / 8 GiB RAM / 128 GiB SSD. Preferred:
4-8 cores / 16 GiB / 256 GiB+. No GPU required. Secure Boot may remain
enabled. Network: Ethernet or Wi-Fi 5+ — neither is hardcoded.

## 5. Upstream components

| Component | Pin | Role | Source |
|-----------|-----|------|--------|
| Hermes Agent | **v0.21.0** (git tag `v2026.8.31`) | agent runtime + A2A | github.com/NousResearch/hermes-agent |
| jñāpakaṁ | **0.5.1** (commit `7fa08bb`) | agent continuity: identity, memory, lineage, seals | github.com/yablokolabs/jnaapakam |
| Restate | **v1.7.2** | durable workflow execution | github.com/restatedev/restate |
| uv | **0.12.10** | offline Python environment tooling | github.com/astral-sh/uv |

> Note: the brief mentioned Hermes "v0.21.0" — that string is the version
> inside Hermes' `pyproject.toml`, but the repository tags that release as
> `v2026.8.31`. Safe Harbor pins the exact tag `v2026.8.31` (which carries
> Hermes Agent v0.21.0) and never installs `latest`.

Integration boundaries (Safe Harbor core is not hardwired to any of them):

```
SAFE HARBOR CORE (deployment / recovery / validation)
      │
 Integration Layer (safeharbor/integrations/)
      ├── hermes      Hermes owns runtime + A2A
      ├── jnaapakam   jñāpakaṁ owns continuity semantics
      └── restate     Restate owns durable execution
```

New components implement the `Integration` interface
(`safeharbor/integrations/base.py`); core code is not rewritten.

## 6. How do I acquire dependencies?

On the **connected acquisition machine** (this is a Debian build host):

```bash
./acquisition/acquire.sh        # download + verify every locked artifact
./acquisition/verify.sh         # re-verify cached artifacts
```

Everything is driven by `manifest/artifacts.lock` — the single source of
truth. Nothing is downloaded that is not in the lock. `jq` and `python3`
are the only acquisition-machine requirements (hash/verification is Python).

## 7. How do I build the offline bundle?

```bash
make bundle        # acquire --if-missing → verify --strict → assemble → hash
```

or manually:

```bash
./acquisition/acquire.sh --if-missing
./acquisition/verify.sh
./acquisition/assemble.sh
```

Output: `dist/safe-harbor-gen1-0.1.0-amd64.tar.gz` + `.sha256`.

## 8. How do I verify it?

```bash
sha256sum -c safe-harbor-gen1-0.1.0-amd64.tar.gz.sha256
```

Inside the bundle, every artifact is re-verified by the installer against
`manifest/checksums.sha256` before anything is installed. If an artifact is
missing or its hash fails, installation FAILS — it never downloads.

## 9. How do I deploy?

On the Ubuntu manager (after transferring + verifying the bundle):

```bash
sudo ./safe-harbor/deploy/preflight.sh      # checker only — validates target
sudo ./safe-harbor/deploy/bootstrap.sh      # layout + dedicated service account
sudo ./safe-harbor/deploy/install.sh        # verified artifacts → services
safeharbor doctor                           # validate everything
```

Deterministic, idempotent, fail-fast. See `runbooks/DEPLOYMENT.md` and
`runbooks/OFFLINE_INSTALL.md`.

## 10. How do I run `safeharbor doctor`?

```bash
safeharbor status      # fast operational summary
safeharbor doctor      # deep validation (exit 0 = no FAIL, 1 = FAIL)
safeharbor validate    # post-reconstruction validation
```

States: `OK`, `WARN`, `FAIL`, `NOT_CONFIGURED`, `REQUIRES_TEST`.
A running process is never treated as semantic health on its own — every
component is probed at its real health endpoint.

## 11. How do I back up?

```bash
sudo safeharbor backup
```

Captures, per component, a **consistent** snapshot:

| Component | Strategy |
|-----------|----------|
| Restate | quiesced copy (service stopped while data is copied) |
| jñāpakaṁ | official `GET /backup` JSON export (or quiesced SQLite copy) |
| Hermes | quiesced copy of `HERMES_HOME` |
| resident/project state | plain copies |
| generation metadata + reconstruction config | JSON snapshots |

Every file is SHA-256-hashed and listed in `backup-manifest.json` before
the backup is published atomically.

## 12. How do I restore?

```bash
sudo safeharbor restore --dry-run /var/lib/safe-harbor/backups/backup-<ID>
sudo safeharbor restore        /var/lib/safe-harbor/backups/backup-<ID>
```

Restore validates the manifest, re-checks every hash, detects conflicts with
newer state, and requires explicit confirmation. Corrupt or incomplete
backups are refused.

## 13. How do I reconstruct onto another machine?

1. Fresh Ubuntu 26.04.1 on the replacement.
2. Verify + extract the bundle, run preflight/bootstrap/install.
3. `sudo safeharbor restore /path/to/backup-<ID>` (validated, deliberate).
4. `safeharbor doctor` + `safeharbor validate --backup ...`.
5. Verify the jñāpakaṁ identity URN (`curl 127.0.0.1:8889/agent`) matches.
6. `safeharbor a2a-test` to reconnect the Specialist.
7. `sudo safeharbor backup --note "post-replacement"`.

Recovery never assumes the original Manager OS is still accessible.
See `runbooks/REPLACEMENT_MACHINE.md`.

## 14. What has actually been tested?

### Status matrix (updated from actual results)

```
Capability                        Status
------------------------------------------------------------
Manifest system                   TESTED
Artifact lock parsing             TESTED
SHA-256 verification              TESTED
Corrupt/missing artifact rejection TESTED
Offline acquisition               TESTED
Offline bundle assembly + hash    TESTED
jñāpakaṁ offline wheelhouse install TESTED (Python 3.13)
jñāpakaṁ live adapter (status/backup) TESTED (real 0.5.1 server)
Restate live adapter (health/backup)  TESTED (real v1.7.2 binary)
State/software separation         TESTED
Backup manifest generation        TESTED
Backup validation + corrupt reject TESTED
Restore dry-run + conflict detect TESTED
Generation manifest               TESTED
CLI exit codes                    TESTED
Integration adapter boundaries    TESTED
Bash syntax / systemd units       TESTED
CI: pytest on 3.11/3.12/3.13      TESTED (GitHub Actions, every push)
CI: shellcheck + bash -n           TESTED (GitHub Actions)
Ubuntu preflight                  LOCALLY SIMULATED (honest FAIL on sub-spec hosts)
Offline bundle on GitHub Release  TESTED (v0.1.0: PyPI + bundle artifacts)
Wheelhouse deterministic rebuild TESTED (byte-identical across Debian + Ubuntu CI)
Ubuntu deployment                 REQUIRES INTEGRATION
Hermes installation (offline env) REQUIRES INTEGRATION
Restate systemd service lifecycle REQUIRES INTEGRATION
Backup with real systemd services REQUIRES INTEGRATION
Replacement-machine recovery      REQUIRES INTEGRATION
A2A discovery                     REQUIRES INTEGRATION
A2A bidirectional tasks           REQUIRES INTEGRATION
A2A bounded capability            REQUIRES INTEGRATION
Reboot/resume                     REQUIRES INTEGRATION
```

Every `REQUIRES INTEGRATION` entry means the step is scripted and the
harness/runbook is executable, but the real Ubuntu manager / Windows
specialist pair has not executed it. Nothing here is pre-filled as PASS.

### Honest notes

- jñāpakaṁ's LLM features (ingest summarization, `/query`, `/reconcile`)
  need a configured model API key; identity, `/status`, search and the
  `/backup` export work without one. Observed live against 0.5.1.
- Restate's ingress (8080) and admin (9070) bind all interfaces by default
  (no bind-address config key exists — verified via `--dump-config`);
  Gen1 restricts them with explicit firewall rules, never silently.
- Hermes' full Python environment cannot be constructed fully offline in
  Gen1 without a complete wheelhouse — source is vendored and the step is
  marked `REQUIRES_INTEGRATION_TEST` (documented in OFFLINE_INSTALL.md).

---

## Repository layout

```
safe-harbor/
├── README.md  LICENSE  Makefile  pyproject.toml
├── manifest/            versions.lock, artifacts.lock, checksums.sha256
├── acquisition/         acquire.sh, verify.sh, assemble.sh, acquire_core.py
├── deploy/              preflight.sh, bootstrap.sh, install.sh, uninstall.sh
├── config/              hermes/, jnaapakam/, restate/, a2a/, .env.example
├── systemd/             restate.service, jnaapakam.service, hermes-manager.service
├── safeharbor/          Python CLI + integrations
├── scripts/             backup.sh, restore.sh, rollback.sh
├── tests/               unit/ integration/ fixtures (pytest)
├── runbooks/            DEPLOYMENT, OFFLINE_INSTALL, A2A_SMOKE_TEST,
│                        BACKUP_RESTORE, ROLLBACK, REBOOT_RESUME, REPLACEMENT_MACHINE
└── dist/                built offline bundle (generated)
```

## Security posture

- A2A: explicit bind (`A2A_HOST`), bearer auth (`A2A_BEARER_TOKEN`),
  per-peer credentials (`A2A_PEER_TOKENS`), trusted-peer allow-list
  (`A2A_TRUSTED_PEERS`), audit log (`$HERMES_HOME/a2a_audit.jsonl`).
  No public listener, no port forwarding, no unrestricted remote admin.
- Secrets are never committed: templates only (`.env.example`), secrets
  generated at install (mode 0600), never in systemd units or manifests.
- Uninstall never deletes resident state; `--purge` is a distinct explicit
  operation.

## Development

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest tests/     # 79 tests, all safe on any machine
make check                             # bash -n + python compile + shellcheck (if present)
make bundle                            # build the offline bundle
```

## Distribution (PyPI)

The `safeharbor` CLI is published to [PyPI](https://pypi.org/project/safeharbor/)
via trusted publishing (OIDC) — no tokens are stored in this repository.

The workflow `.github/workflows/pypi.yml` runs on every `v*` tag, verifies the
tag matches the version in `pyproject.toml`, builds the sdist + wheel, and
uploads. The CLI has zero runtime dependencies and works fully offline once
installed, so PyPI is purely a distribution channel for the tool itself —
deploying a target node still happens from the verified offline bundle.

```bash
pip install safeharbor        # or: pipx install safeharbor
safeharbor version
```

To release a new version:

```bash
# bump version in pyproject.toml, commit, then:
git tag v0.2.0
git push origin v0.2.0        # workflow publishes automatically
```

First-time trusted-publisher setup (already done for v0.1.0):
[pypi.org/manage/account/publishing](https://pypi.org/manage/account/publishing/)
— owner `yablokolabs`, repository `safe-harbor`, workflow `pypi.yml`,
environment `pypi`.

## License

MIT — see `LICENSE`. Upstream licenses: Hermes Agent MIT, jñāpakaṁ MIT,
uv MIT OR Apache-2.0, Restate Business Source License 1.1 (recorded in
`manifest/versions.lock`).