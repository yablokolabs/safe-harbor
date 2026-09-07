"""Backup: manifest generation, validation, corrupt-backup rejection."""

from __future__ import annotations

import json
from pathlib import Path

from safeharbor import backup as backup_mod
from safeharbor.checksums import sha256_file
from safeharbor.context import Context
from safeharbor.manifest import (
    BackupComponent,
    BackupEntry,
    BackupManifest,
    read_backup_manifest,
    validate_backup_manifest,
    write_backup_manifest,
)


def _seed_resident(tmp_layout, name="SOUL.md"):
    resident = tmp_layout.resident_dir
    resident.mkdir(parents=True, exist_ok=True)
    (resident / name).write_text("# resident data", encoding="utf-8")


def test_backup_manifest_generation(tmp_layout, ctx):
    _seed_resident(tmp_layout)
    assert backup_mod.run_backup(ctx) == 0
    backups = list(tmp_layout.backup_dir.glob("backup-*"))
    assert len(backups) == 1
    manifest = read_backup_manifest(backups[0])
    assert manifest.schema_version == 1
    assert manifest.backup_id.startswith("backup-")
    # resident soul file must be captured under jnaapakam
    jnaa = manifest.components.get("jnaapakam")
    assert jnaa is not None
    rels = [e.relpath for e in jnaa.entries]
    assert any("SOUL.md" in r for r in rels)


def test_backup_validates_clean(tmp_layout, ctx):
    _seed_resident(tmp_layout)
    backup_mod.run_backup(ctx)
    latest = sorted(tmp_layout.backup_dir.glob("backup-*"))[-1]
    problems, warnings = validate_backup_manifest(latest)
    assert problems == []


def test_backup_hash_mismatch_rejected(tmp_layout, ctx):
    _seed_resident(tmp_layout)
    backup_mod.run_backup(ctx)
    latest = sorted(tmp_layout.backup_dir.glob("backup-*"))[-1]
    # corrupt one staged file; validation must now fail
    for f in latest.rglob("SOUL.md"):
        f.write_text("# tampered", encoding="utf-8")
    problems, _ = validate_backup_manifest(latest)
    assert problems, "tampered backup must fail validation"
    assert any("hash mismatch" in p for p in problems)


def test_backup_missing_file_rejected(tmp_layout, ctx):
    _seed_resident(tmp_layout)
    backup_mod.run_backup(ctx)
    latest = sorted(tmp_layout.backup_dir.glob("backup-*"))[-1]
    for f in latest.rglob("SOUL.md"):
        f.unlink()
    problems, _ = validate_backup_manifest(latest)
    assert any("missing file" in p for p in problems)


def test_backup_without_manifest_rejected(tmp_layout, ctx):
    _seed_resident(tmp_layout)
    backup_mod.run_backup(ctx)
    latest = sorted(tmp_layout.backup_dir.glob("backup-*"))[-1]
    (latest / "backup-manifest.json").unlink()
    problems, _ = validate_backup_manifest(latest)
    assert problems and "no manifest" in problems[0]


def test_backup_wrong_schema_rejected(tmp_path):
    fake = tmp_path / "backup-x"
    fake.mkdir()
    manifest = BackupManifest(
        backup_id="backup-x",
        created_at="2026-09-07T00:00:00+00:00",
        created_by="test",
        schema_version=99,
        safe_harbor_generation=1,
        components={},
        generation_snapshot={},
        reconstruction={},
    )
    write_backup_manifest(fake, manifest)
    problems, _ = validate_backup_manifest(fake)
    assert any("schema" in p for p in problems)


def test_backup_manifest_roundtrip(tmp_path):
    manifest = BackupManifest(
        backup_id="backup-1",
        created_at="2026-09-07T00:00:00+00:00",
        created_by="safeharbor test",
        schema_version=1,
        safe_harbor_generation=1,
        components={
            "restate": BackupComponent(
                name="restate",
                strategy="quiesced_copy",
                entries=[BackupEntry(relpath="restate/n/data", sha256="ab" * 32, size=42)],
            )
        },
        generation_snapshot={"components": {"restate": {"version": "v1.7.2"}}},
        reconstruction={},
    )
    path = write_backup_manifest(tmp_path, manifest)
    loaded = read_backup_manifest(tmp_path)
    assert loaded.backup_id == "backup-1"
    assert loaded.components["restate"].strategy == "quiesced_copy"
    assert loaded.components["restate"].entries[0].sha256 == "ab" * 32
    assert path.is_file()


def test_backup_skipped_components_recorded(tmp_layout, ctx):
    """Components without resident data are recorded as 'skipped', not fatal."""
    backup_mod.run_backup(ctx)
    latest = sorted(tmp_layout.backup_dir.glob("backup-*"))[-1]
    manifest = read_backup_manifest(latest)
    assert "restate" in manifest.components
    assert manifest.components["restate"].strategy in ("skipped", "quiesced_copy")