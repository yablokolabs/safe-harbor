#!/usr/bin/env python3
"""Safe Harbor offline acquisition core.

Stage A — connected acquisition machine:

    read lock manifest
        -> acquire exact artifacts
        -> verify source/version
        -> calculate/verify hashes
        -> assemble offline bundle
        -> hash bundle

Every artifact, hash and URL comes from manifest/artifacts.lock. Nothing is
downloaded that is not in the lock, and nothing is downloaded silently on
the target — the target only ever consumes a pre-verified bundle.

Commands:

    python3 acquire_core.py acquire [--if-missing]
    python3 acquire_core.py verify [--strict]
    python3 acquire_core.py assemble

Exit codes: 0 success, 1 verification failure, 2 usage.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tarfile
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_DIR = REPO_ROOT / "manifest"
CACHE_DIR = REPO_ROOT / "acquisition" / "cache"
DIST_DIR = REPO_ROOT / "dist"

VERSION = "0.1.0"
ARCH = "amd64"


class AcquireError(Exception):
    pass


# ---------------------------------------------------------------------------
# Lock reading
# ---------------------------------------------------------------------------


def load_lock() -> dict:
    path = MANIFEST_DIR / "artifacts.lock"
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    artifacts = data.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise AcquireError(f"{path}: no 'artifacts' list")
    return data


def artifact_path(entry: dict) -> Path:
    return CACHE_DIR / entry["component"] / entry["artifact_filename"]


# ---------------------------------------------------------------------------
# Hashing / verification
# ---------------------------------------------------------------------------


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fetch(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".part")
    try:
        urllib.request.urlretrieve(url, tmp)  # noqa: S310 — acquisition machine is connected by design
        tmp.replace(dest)
    finally:
        if tmp.exists():
            tmp.unlink()


def verify_entry(entry: dict, path: Path) -> tuple[bool, str]:
    """Verify one artifact. Returns (ok, detail)."""
    if not path.is_file():
        return False, f"missing artifact: {path}"
    expected = entry.get("sha256", "")
    actual = sha256_file(path)
    if not expected:
        return False, f"{entry['artifact_filename']}: lock has no sha256"
    if actual != expected:
        return False, (
            f"{entry['artifact_filename']}: SHA-256 mismatch\n"
            f"  expected {expected}\n"
            f"  actual   {actual}"
        )
    return True, f"{entry['artifact_filename']}: SHA-256 verified"


def verify_upstream(entry: dict, path: Path) -> tuple[bool, str]:
    """Verify against the upstream-published checksum when one exists."""
    expected = entry.get("upstream_checksum")
    if not expected:
        return True, (
            f"{entry['artifact_filename']}: no upstream checksum published "
            "(self-computed hash recorded; see upstream_checksum_source)"
        )
    actual = sha256_file(path)
    if actual != expected:
        return False, (
            f"{entry['artifact_filename']}: does NOT match upstream checksum "
            f"{entry.get('upstream_checksum_source', '?')}"
        )
    return True, f"{entry['artifact_filename']}: matches upstream checksum"


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def cmd_acquire(if_missing: bool) -> int:
    lock = load_lock()
    ok = True
    report: list[str] = []
    for entry in lock["artifacts"]:
        path = artifact_path(entry)
        url = entry.get("url", "")
        if path.is_file() and if_missing:
            verified, detail = verify_entry(entry, path)
            ok = ok and verified
            report.append(f"cached   {detail}")
            continue
        if not url:
            print(f"FAIL: {entry['artifact_filename']} has no url in lock", file=sys.stderr)
            ok = False
            continue
        print(f"acquiring {entry['artifact_filename']} ...")
        fetch(url, path)
        verified, detail = verify_entry(entry, path)
        ok = ok and verified
        if verified:
            upstream_ok, upstream_detail = verify_upstream(entry, path)
            ok = ok and upstream_ok
            report.append(f"acquired {detail}; {upstream_detail}")
        else:
            report.append(f"FAILED   {detail}")
    write_report(report)
    return 0 if ok else 1


def cmd_verify(strict: bool) -> int:
    lock = load_lock()
    ok = True
    report: list[str] = []
    for entry in lock["artifacts"]:
        path = artifact_path(entry)
        verified, detail = verify_entry(entry, path)
        ok = ok and verified
        report.append(("verified " if verified else "FAILED   ") + detail)
        if verified:
            upstream_ok, upstream_detail = verify_upstream(entry, path)
            ok = ok and upstream_ok
            report.append(("verified " if upstream_ok else "FAILED   ") + upstream_detail)
    write_report(report)
    if ok:
        print("All locked artifacts verified.")
    else:
        print("VERIFICATION FAILED — see acquisition/cache/verification-report.txt", file=sys.stderr)
    return 0 if ok else 1


def write_report(lines: list[str]) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    header = f"# Safe Harbor acquisition report — {stamp}\n"
    (CACHE_DIR / "verification-report.txt").write_text(
        header + "\n".join(lines) + "\n", encoding="utf-8"
    )


def _copy_tree(src: Path, dest: Path, *, exclude: tuple[str, ...]) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    for path in src.iterdir():
        if path.name in exclude:
            continue
        target = dest / path.name
        if path.is_dir():
            shutil.copytree(path, target, ignore=shutil.ignore_patterns(*exclude))
        else:
            shutil.copy2(path, target)


def cmd_assemble() -> int:
    """Assemble the offline bundle from verified artifacts + this repo."""
    lock = load_lock()

    # Every artifact must be present AND verified before assembly.
    for entry in lock["artifacts"]:
        path = artifact_path(entry)
        verified, detail = verify_entry(entry, path)
        if not verified:
            print(f"REFUSED: {detail}", file=sys.stderr)
            print("Run `python3 acquire_core.py acquire` first.", file=sys.stderr)
            return 1

    bundle_name = f"safe-harbor-gen1-{VERSION}-{ARCH}"
    stage = DIST_DIR / ".stage" / bundle_name
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)

    # 1. The Safe Harbor repository itself (excludes VCS/venv/build output).
    _copy_tree(REPO_ROOT, stage / "safe-harbor", exclude=(".git", ".venv", "venv", "dist", "__pycache__", ".pytest_cache", "acquisition"))

    # 2. Verified upstream artifacts, organised by component.
    artifacts_dir = stage / "artifacts"
    for entry in lock["artifacts"]:
        src = artifact_path(entry)
        target = artifacts_dir / entry["component"] / entry["artifact_filename"]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, target)

    # 3. Lock manifests travel with the bundle.
    shutil.copytree(MANIFEST_DIR, stage / "manifest")

    # 4. Quick-start note.
    (stage / "BUNDLE.txt").write_text(
        "\n".join(
            [
                f"Safe Harbor Gen1 offline bundle — {bundle_name}",
                "",
                "Verification (on the air-gapped target):",
                "  sha256sum -c safe-harbor-gen1-0.1.0-amd64.tar.gz.sha256",
                "",
                "Extract:",
                "  tar -xzf safe-harbor-gen1-0.1.0-amd64.tar.gz",
                "",
                "Install (as root on the Ubuntu manager):",
                "  sudo ./safe-harbor-gen1-0.1.0-amd64/safe-harbor/deploy/preflight.sh",
                "  sudo ./safe-harbor-gen1-0.1.0-amd64/safe-harbor/deploy/install.sh",
                "",
                "Then validate:",
                "  safeharbor doctor",
                "",
                "Full documentation: safe-harbor/runbooks/ and README.md",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    # 5. Archive + hash.
    tarball = DIST_DIR / f"{bundle_name}.tar.gz"
    tarball.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(tarball, "w:gz") as tf:
        tf.add(stage, arcname=bundle_name)

    bundle_hash = sha256_file(tarball)
    (DIST_DIR / f"{bundle_name}.tar.gz.sha256").write_text(
        f"{bundle_hash}  {tarball.name}\n", encoding="utf-8"
    )

    print(f"Bundle: {tarball}")
    print(f"SHA-256: {bundle_hash}")
    print(f"SHA-256 file: {DIST_DIR / (bundle_name + '.tar.gz.sha256')}")

    contents = [str(p.relative_to(stage)) for p in sorted(stage.rglob("*")) if p.is_file()]
    print(f"Contents: {len(contents)} files")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print(__doc__)
        return 2
    command = argv[0]
    if command == "acquire":
        return cmd_acquire("--if-missing" in argv)
    if command == "verify":
        return cmd_verify("--strict" in argv)
    if command == "assemble":
        return cmd_assemble()
    print(f"unknown command: {command}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())