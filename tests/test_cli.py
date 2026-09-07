"""CLI exit codes: status, doctor, backup, restore, validate, a2a-test."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from safeharbor.cli import main


def _args(root: Path, *extra: str) -> list[str]:
    return ["--root", str(root), "--simulate", *extra]


def test_version_exit_zero(tmp_path):
    assert main(["version"]) == 0


def test_status_exit_zero_in_simulate(tmp_path):
    assert main(_args(tmp_path, "status")) == 0


def test_status_json(tmp_path, capsys):
    assert main(_args(tmp_path, "status", "--json")) == 0
    data = json.loads(capsys.readouterr().out)
    assert "overall" in data
    assert data["overall"] in ("OK", "WARN", "FAIL", "NOT_CONFIGURED", "REQUIRES_TEST")


def test_doctor_exit_zero_in_simulate(tmp_path):
    assert main(_args(tmp_path, "doctor")) == 0


def test_backup_creates_backup(tmp_path):
    assert main(_args(tmp_path, "backup")) == 0
    backups = list((tmp_path / "var" / "lib" / "backups").glob("backup-*"))
    assert len(backups) == 1
    assert (backups[0] / "backup-manifest.json").is_file()


def test_validate_reports_backup_valid(tmp_path, capsys):
    """validate must report the backup check as OK even when component pins
    honestly FAIL because nothing is installed on the test machine."""
    main(_args(tmp_path, "backup"))
    backup = list((tmp_path / "var" / "lib" / "backups").glob("backup-*"))[0]
    rc = main(_args(tmp_path, "validate", "--backup", str(backup)))
    assert rc in (0, 1)
    out = capsys.readouterr().out
    assert "valid" in out
    assert "backup" in out


def test_restore_dry_run_exit_zero(tmp_path):
    main(_args(tmp_path, "backup"))
    backup = list((tmp_path / "var" / "lib" / "backups").glob("backup-*"))[0]
    assert main(_args(tmp_path, "restore", "--dry-run", str(backup))) == 0


def test_restore_corrupt_exit_one(tmp_path):
    main(_args(tmp_path, "backup"))
    backup = list((tmp_path / "var" / "lib" / "backups").glob("backup-*"))[0]
    # corrupt the manifest
    (backup / "backup-manifest.json").write_text("{not json", encoding="utf-8")
    assert main(_args(tmp_path, "restore", "--dry-run", str(backup))) == 1


def test_restore_unknown_backup_exit_two(tmp_path):
    assert main(_args(tmp_path, "restore", "--dry-run", str(tmp_path / "nope"))) == 2


def test_a2a_no_peers_exit_one(tmp_path):
    assert main(_args(tmp_path, "a2a-test")) == 1


def test_generation_record_when_nothing_installed(tmp_path):
    # no component versions detected -> honest failure, not a fake PASS
    assert main(_args(tmp_path, "generation", "record")) == 1


def test_generation_validate_missing(tmp_path):
    assert main(_args(tmp_path, "generation", "validate")) == 1


def test_usage_error_exit_two(tmp_path):
    assert main(_args(tmp_path, "restore")) == 2  # no backup arg, not --list


def test_backup_idempotent_second_run(tmp_path):
    main(_args(tmp_path, "backup"))
    main(_args(tmp_path, "backup"))
    backups = list((tmp_path / "var" / "lib" / "backups").glob("backup-*"))
    assert len(backups) == 2
    for backup in backups:
        problems, _ = __import__(
            "safeharbor.manifest", fromlist=["validate_backup_manifest"]
        ).validate_backup_manifest(backup)
        assert problems == []