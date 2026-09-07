"""Bash scripts: syntax validity + safe local behavior (preflight, dry-run).

These tests never execute a script that would modify the machine:
* bash -n only parses
* preflight.sh is a checker only
* install.sh --dry-run prints intent without changing anything
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent

SHELL_SCRIPTS = sorted(
    list((REPO / "acquisition").glob("*.sh"))
    + list((REPO / "deploy").glob("*.sh"))
    + list((REPO / "scripts").glob("*.sh"))
)


@pytest.mark.parametrize("script", SHELL_SCRIPTS, ids=lambda p: str(p.relative_to(REPO)))
def test_bash_syntax(script):
    proc = subprocess.run(
        ["bash", "-n", str(script)], capture_output=True, text=True, timeout=30
    )
    assert proc.returncode == 0, f"{script.name}: {proc.stderr}"


def test_preflight_runs_safely():
    """preflight.sh is a checker. It must run anywhere without crashing and
    report honestly: exit 0 when no check FAILs, exit 1 when the host misses
    a Gen1 minimum (this dev box may legitimately be below the 128 GiB disk
    minimum). Either outcome is a correct, honest result."""
    proc = subprocess.run(
        ["bash", str(REPO / "deploy" / "preflight.sh")],
        capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode in (0, 1), f"preflight crashed:\n{proc.stdout}\n{proc.stderr}"
    assert "distribution" in proc.stdout
    assert "preflight result" in proc.stdout


def test_install_dry_run_runs_safely():
    """install.sh --dry-run must print its plan without touching the system."""
    proc = subprocess.run(
        ["bash", str(REPO / "deploy" / "install.sh"), "--dry-run"],
        capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode == 0, f"install dry-run failed:\n{proc.stdout}\n{proc.stderr}"
    assert "DRY-RUN" in proc.stdout
    assert "would install Restate" in proc.stdout


def test_uninstall_requires_root_when_not_dry():
    """uninstall.sh must refuse without root (never partially run)."""
    proc = subprocess.run(
        ["bash", str(REPO / "deploy" / "uninstall.sh")],
        capture_output=True, text=True, timeout=30,
    )
    assert proc.returncode == 1
    assert "root" in proc.stderr


def test_systemd_units_exist_and_are_parseable():
    """Every unit referenced by the installer exists and is non-empty."""
    units = ["restate.service", "jnaapakam.service", "hermes-manager.service"]
    for unit in units:
        path = REPO / "systemd" / unit
        assert path.is_file(), f"missing {unit}"
        text = path.read_text(encoding="utf-8")
        assert "[Unit]" in text and "[Service]" in text and "[Install]" in text
        assert "ExecStart=" in text