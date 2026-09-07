# Acquisition (Stage A — connected machine)

This directory implements the offline-first supply chain. Everything is
driven by `../manifest/artifacts.lock`.

```
read lock manifest
    → acquire exact artifacts
    → verify source/version
    → calculate/verify hashes
    → assemble offline bundle
    → hash bundle
```

## Files

| File | Purpose |
|------|---------|
| `acquire.sh` | wrapper: download + verify every locked artifact |
| `verify.sh` | wrapper: re-verify the cache (never downloads) |
| `assemble.sh` | wrapper: build `dist/safe-harbor-gen1-<version>-<arch>.tar.gz` |
| `acquire_core.py` | the actual logic (lock parsing, hashing, verification, assembly) |
| `cache/` | acquired artifacts (generated, git-ignored) |

## Artifacts

All URLs, versions and SHA-256 values come from `manifest/artifacts.lock`
(the authoritative record). Two verification tiers are recorded per
artifact:

- `verified-against-upstream` — the hash also matches an upstream-published
  checksum (`sha256.sum` for Restate, `.sha256` files for uv).
- `hash-recorded` — no upstream per-artifact checksum is published for
  codeload source tarballs; the SHA-256 is computed by Safe Harbor and the
  source is pinned by exact tag/commit.

The Python wheelhouse (`jnaapakam-wheels-cp313-amd64.tar.gz`) is built
locally with `pip download` and hashed; it is recorded as
`built-and-hashed`.

## Verification report

`cache/verification-report.txt` is written by every acquire/verify run with
per-artifact results and a timestamp.

## Safety rules

- Never downloads an artifact that is not in the lock.
- Never reaches the Internet from the target (the installer verifies
  pre-transferred artifacts only; missing/corrupt → FAIL, no download).
- Assemble refuses to build a bundle with a missing or unverified artifact.