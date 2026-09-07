"""Manifest system tests: parsing, validation, corruption rejection."""

from __future__ import annotations

import json

import pytest

from safeharbor.manifest import (
    ManifestError,
    build_generation_manifest,
    load_artifact_lock,
    load_version_lock,
    read_checksums,
    validate_generation_manifest,
    write_checksums,
    write_generation_manifest,
)
from safeharbor.paths import Layout

REPO = __import__("pathlib").Path(__file__).resolve().parent.parent


def test_version_lock_parses():
    """The committed versions.lock must parse and validate."""
    lock = load_version_lock(REPO / "manifest" / "versions.lock")
    assert {"hermes", "jnaapakam", "restate", "uv"} <= set(lock["components"])


def test_version_lock_rejects_missing_keys(tmp_path):
    path = tmp_path / "bad.lock"
    path.write_text(json.dumps({"components": {"hermes": {"version": "x"}}}), encoding="utf-8")
    with pytest.raises(ManifestError, match="missing key"):
        load_version_lock(path)


def test_artifact_lock_parses():
    """The committed artifacts.lock must parse and validate."""
    lock = load_artifact_lock(REPO / "manifest" / "artifacts.lock")
    names = {a["component"] for a in lock["artifacts"]}
    assert {"hermes", "jnaapakam", "restate", "uv"} <= names
    # every artifact carries a real 64-hex sha256
    for artifact in lock["artifacts"]:
        assert len(artifact["sha256"]) == 64


def test_artifact_lock_rejects_empty(tmp_path):
    path = tmp_path / "bad.lock"
    path.write_text(json.dumps({"artifacts": []}), encoding="utf-8")
    with pytest.raises(ManifestError, match="non-empty"):
        load_artifact_lock(path)


def test_checksums_roundtrip(tmp_path):
    hashes = {"a.tar.gz": "ab" * 32, "b/b.tar.gz": "cd" * 32}
    path = tmp_path / "checksums.sha256"
    write_checksums(path, hashes)
    assert read_checksums(path) == hashes


def test_checksums_ignores_comments_and_blank(tmp_path):
    path = tmp_path / "checksums.sha256"
    path.write_text("# comment\n\n" + f"{'ab' * 32}  x.tar.gz\n", encoding="utf-8")
    assert read_checksums(path) == {"x.tar.gz": "ab" * 32}


def test_generation_manifest_build_and_validate(tmp_layout):
    manifest = build_generation_manifest(
        components={"hermes": {"version": "v0.21.0"}, "restate": {"version": "v1.7.2"}}
    )
    validate_generation_manifest(manifest)
    assert manifest["safe_harbor_generation"] == 1
    # resident identity must NOT be bound to machine identity
    assert "hostname" not in manifest
    assert "mac" not in manifest


def test_generation_manifest_write_read(tmp_layout):
    manifest = build_generation_manifest(components={"restate": {"version": "v1.7.2"}})
    path = write_generation_manifest(tmp_layout, manifest)
    assert path.is_file()
    current = tmp_layout.generations_dir / "current.json"
    assert current.is_file()
    validate_generation_manifest(json.loads(current.read_text(encoding="utf-8")))


def test_generation_manifest_rejects_wrong_schema(tmp_path):
    with pytest.raises(ManifestError):
        validate_generation_manifest({"safe_harbor_generation": 99, "components": {}, "created_at": "x"})