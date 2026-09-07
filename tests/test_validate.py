"""Validation tests: separation, structure, generation, continuity."""

from __future__ import annotations

from pathlib import Path

from safeharbor import validate
from safeharbor.checksums import sha256_file
from safeharbor.manifest import build_generation_manifest, write_generation_manifest


def test_separation_ok(tmp_layout, ctx):
    results = validate.validate_all(ctx)
    sep = next(r for r in results if r.name == "separation")
    assert sep.state == "OK"


def test_separation_fails_when_state_inside_software(tmp_path):
    from safeharbor.context import Context
    from safeharbor.paths import Layout

    # deliberately bad layout: resident state inside software tree
    layout = Layout(
        software_dir=tmp_path / "opt" / "software",
        config_dir=tmp_path / "etc",
        state_dir=tmp_path / "opt" / "software" / "state",  # overlap!
        log_dir=tmp_path / "logs",
        backup_dir=tmp_path / "backups",
    )
    layout.software_dir.mkdir(parents=True, exist_ok=True)
    layout.state_dir.mkdir(parents=True, exist_ok=True)
    layout.resident_dir.mkdir(parents=True, exist_ok=True)
    ctx = Context(layout=layout, simulate=True)
    results = validate.validate_all(ctx)
    sep = next(r for r in results if r.name == "separation")
    assert sep.state == "FAIL"
    assert "software" in sep.detail


def test_structure_check(tmp_layout, ctx):
    results = validate.validate_all(ctx)
    struct = next(r for r in results if r.name == "structure")
    assert struct.state == "OK"


def test_generation_recorded_is_valid(tmp_layout, ctx):
    manifest = build_generation_manifest(components={"restate": {"version": "v1.7.2"}})
    write_generation_manifest(tmp_layout, manifest)
    results = validate.validate_all(ctx)
    gen = next(r for r in results if r.name == "generation")
    assert gen.state == "OK"


def test_manager_os_check_honest(tmp_layout, ctx):
    """The manager-OS check must run on any host and only ever fail on a
    genuinely unsupported OS (it reports the build machine honestly)."""
    from safeharbor import status

    result = status._manager_os_check(ctx)
    # On the Debian build machine: WARN. On the Ubuntu target: OK.
    # Anything else (FAIL) would mean a supported host was rejected.
    assert result.state in ("OK", "WARN")
    assert result.detail


def test_status_exit_zero_when_only_warn(tmp_layout, ctx):
    from safeharbor import status

    assert status.run(ctx) == 0  # WARN/NOT_CONFIGURED only -> pass exit code


def test_doctor_has_no_unexpected_failures(tmp_layout, ctx):
    from safeharbor import doctor

    results = doctor.doctor_checks(ctx)
    failed = [r for r in results if r.state == "FAIL"]
    assert failed == [], f"unexpected FAIL: {[(r.name, r.detail) for r in failed]}"