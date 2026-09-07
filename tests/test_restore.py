"""Restore: dry-run, conflict detection, corrupt-backup refusal."""

from __future__ import annotations

from pathlib import Path

from safeharbor import backup as backup_mod
from safeharbor import restore
from safeharbor.manifest import (
    BackupComponent,
    BackupEntry,
    BackupManifest,
    build_generation_manifest,
    write_backup_manifest,
    write_generation_manifest,
)


def _make_backup(tmp_layout, ctx, *, generation_created=None):
    """Create a valid backup with one resident file."""
    resident = tmp_layout.resident_dir
    resident.mkdir(parents=True, exist_ok=True)
    (resident / "SOUL.md").write_text("# resident", encoding="utf-8")
    backup_mod.run_backup(ctx)
    backup = sorted(tmp_layout.backup_dir.glob("backup-*"))[-1]
    if generation_created:
        manifest = build_generation_manifest(components={"restate": {"version": "v1.7.2"}})
        manifest["created_at"] = generation_created
        write_generation_manifest(tmp_layout, manifest)
    return backup


def test_dry_run_ok(tmp_layout, ctx):
    backup = _make_backup(tmp_layout, ctx)
    plan = restore.plan_restore(backup, ctx)
    assert plan.ok
    assert restore.dry_run(backup, ctx) == 0


def test_dry_run_refuses_corrupt(tmp_layout, ctx):
    backup = _make_backup(tmp_layout, ctx)
    for f in backup.rglob("SOUL.md"):
        f.write_text("# tampered", encoding="utf-8")
    plan = restore.plan_restore(backup, ctx)
    assert not plan.ok
    assert restore.dry_run(backup, ctx) == 1


def test_dry_run_refuses_missing_manifest(tmp_layout, ctx):
    backup = _make_backup(tmp_layout, ctx)
    (backup / "backup-manifest.json").unlink()
    assert restore.dry_run(backup, ctx) == 1


def test_conflict_newer_state_detected(tmp_layout, ctx):
    # backup created now, then a newer generation recorded → conflict
    backup = _make_backup(tmp_layout, ctx)
    manifest = build_generation_manifest(components={"restate": {"version": "v1.7.2"}})
    manifest["created_at"] = "2026-12-31T00:00:00+00:00"  # newer than backup
    write_generation_manifest(tmp_layout, manifest)
    plan = restore.plan_restore(backup, ctx)
    assert plan.conflicts
    assert not plan.ok


def test_force_bypasses_conflict(tmp_layout, ctx):
    backup = _make_backup(tmp_layout, ctx)
    manifest = build_generation_manifest(components={"restate": {"version": "v1.7.2"}})
    manifest["created_at"] = "2026-12-31T00:00:00+00:00"
    write_generation_manifest(tmp_layout, manifest)
    plan = restore.plan_restore(backup, ctx, force=True)
    assert plan.ok


def test_restore_requires_confirmation_without_yes(tmp_layout, ctx, monkeypatch):
    backup = _make_backup(tmp_layout, ctx)
    monkeypatch.setattr("builtins.input", lambda _prompt: "not-yes")
    assert restore.run(backup, ctx, dry=False, yes=False) == 1


def test_restore_with_yes_performs(tmp_layout, ctx):
    backup = _make_backup(tmp_layout, ctx)
    assert restore.run(backup, ctx, dry=False, yes=True) == 0
    # reconstruction generation recorded
    current = tmp_layout.generations_dir / "current.json"
    assert current.is_file()
    assert "restored from backup" in current.read_text(encoding="utf-8")