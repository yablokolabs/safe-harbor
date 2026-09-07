"""SHA-256 verification: good artifacts pass, corrupt/missing are rejected."""

from __future__ import annotations

from pathlib import Path

from safeharbor.checksums import sha256_bytes, sha256_file, verify_sha256
from acquisition.acquire_core import cmd_assemble, verify_entry


def test_sha256_bytes_stable():
    assert sha256_bytes(b"hello") == (
        "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
    )


def test_verify_sha256_ok(tmp_path):
    path = tmp_path / "f.txt"
    path.write_bytes(b"hello")
    assert verify_sha256(path, sha256_file(path))
    assert not verify_sha256(path, "0" * 64)


def test_artifact_verify_ok(tmp_path):
    artifact = tmp_path / "a.bin"
    artifact.write_bytes(b"artifact-data")
    digest = sha256_file(artifact)
    entry = {"artifact_filename": "a.bin", "sha256": digest}
    ok, detail = verify_entry(entry, artifact)
    assert ok
    assert "verified" in detail


def test_artifact_verify_corrupt_rejected(tmp_path):
    artifact = tmp_path / "a.bin"
    artifact.write_bytes(b"artifact-data")
    entry = {"artifact_filename": "a.bin", "sha256": "0" * 64}
    ok, detail = verify_entry(entry, artifact)
    assert not ok
    assert "mismatch" in detail


def test_artifact_missing_rejected(tmp_path):
    entry = {"artifact_filename": "gone.bin", "sha256": "0" * 64}
    ok, detail = verify_entry(entry, tmp_path / "gone.bin")
    assert not ok
    assert "missing" in detail


def test_acquire_refuses_missing_artifact(monkeypatch, tmp_path):
    """assemble must refuse when a locked artifact is absent."""
    lock = {
        "artifacts": [
            {
                "component": "testcomp",
                "version": "1.0",
                "release": "1.0",
                "artifact_filename": "missing.tar.gz",
                "architecture": "amd64",
                "sha256": "0" * 64,
            }
        ]
    }
    import acquisition.acquire_core as acquire_core

    monkeypatch.setattr(acquire_core, "load_lock", lambda: lock)
    assert cmd_assemble() == 1