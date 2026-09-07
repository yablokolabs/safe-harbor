"""`safeharbor validate` — validation useful after migration/reconstruction.

Checks, mirroring the README status matrix:

* environment manifest parses and matches the current Safe Harbor generation
* installed component versions match the pinned version lock
* resident state lives OUTSIDE the software tree (state/software separation)
* persistent-state structure exists
* component state (per integration doctor)
* backup metadata and hashes (a given backup, or the latest one)
* continuity metadata where supported (jñāpakaṁ generation record)
* integration configuration validity
"""

from __future__ import annotations

from pathlib import Path

from .context import Context
from .health import FAIL, NOT_CONFIGURED, OK, WARN, CheckResult, passed, sorted_results, worst
from .integrations import REGISTRY
from .manifest import (
    load_artifact_lock,
    load_current_generation,
    load_version_lock,
    validate_backup_manifest,
    validate_generation_manifest,
)
from .paths import default_layout


def _repo_manifest_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "manifest"


def _separation_check(ctx: Context) -> CheckResult:
    """HARD requirement: software and persistent state must be separate."""
    software = ctx.layout.software_dir
    state = ctx.layout.state_dir
    resident = ctx.layout.resident_dir
    problems: list[str] = []
    if software.is_dir() and state.is_dir():
        try:
            common = Path(software).resolve().is_relative_to(Path(state).resolve()) or Path(
                state
            ).resolve().is_relative_to(Path(software).resolve())
        except TypeError:
            common = False
        if common:
            problems.append("software and state trees overlap")
    if resident.is_dir() and software.is_dir():
        try:
            overlap = Path(resident).resolve().is_relative_to(Path(software).resolve())
        except TypeError:
            overlap = False
        if overlap:
            problems.append("resident state lives under the software tree")
    if problems:
        return CheckResult("separation", FAIL, "; ".join(problems))
    if not resident.is_dir():
        return CheckResult("separation", WARN, "resident dir not created yet")
    return CheckResult("separation", OK, "software and persistent state are separate")


def _pins_check(ctx: Context) -> CheckResult:
    """Installed versions vs the supply-chain lock (best effort)."""
    versions_path = _repo_manifest_dir() / "versions.lock"
    if not versions_path.is_file():
        return CheckResult("pins", NOT_CONFIGURED, "versions.lock not present in this checkout")
    try:
        lock = load_version_lock(versions_path)
    except Exception as exc:
        return CheckResult("pins", FAIL, str(exc))
    mismatches: list[str] = []
    checked = 0
    for name, integration in REGISTRY.items():
        pinned = (lock.get("components") or {}).get(name, {}).get("version")
        installed = integration.version(ctx)
        if pinned is None:
            continue
        checked += 1
        if installed is None:
            mismatches.append(f"{name}: pinned {pinned} but not installed")
        elif pinned not in installed:
            mismatches.append(f"{name}: pinned {pinned}, installed {installed}")
    if mismatches:
        return CheckResult("pins", FAIL, "; ".join(mismatches))
    return CheckResult("pins", OK, f"{checked} component(s) match the version lock")


def _generation_check(ctx: Context) -> CheckResult:
    generation = load_current_generation(ctx.layout)
    if generation is None:
        return CheckResult("generation", NOT_CONFIGURED, "no generation manifest recorded")
    try:
        validate_generation_manifest(generation)
    except Exception as exc:
        return CheckResult("generation", FAIL, str(exc))
    components = generation.get("components", {})
    summary = ", ".join(f"{k}={v.get('version', '?')}" for k, v in sorted(components.items()))
    return CheckResult("generation", OK, f"valid manifest ({summary})")


def _structure_check(ctx: Context) -> CheckResult:
    missing = [
        str(p)
        for p in (
            ctx.layout.resident_dir,
            ctx.layout.hermes_dir,
            ctx.layout.jnaapakam_dir,
            ctx.layout.restate_dir,
            ctx.layout.projects_dir,
            ctx.layout.generations_dir,
        )
        if not p.is_dir()
    ]
    if missing:
        return CheckResult("structure", FAIL, "missing dirs: " + ", ".join(missing))
    return CheckResult("structure", OK, "persistent-state structure complete")


def _backup_check(ctx: Context, backup: Path | None) -> CheckResult:
    target = backup
    if target is None:
        backups = sorted(ctx.layout.backup_dir.glob("backup-*")) if ctx.layout.backup_dir.is_dir() else []
        target = backups[-1] if backups else None
    if target is None:
        return CheckResult("backup", NOT_CONFIGURED, "no backup to validate")
    problems, warnings = validate_backup_manifest(target)
    if problems:
        return CheckResult("backup", FAIL, f"{target.name}: {'; '.join(problems)}")
    return CheckResult("backup", OK, f"{target.name} valid")


def _continuity_check(ctx: Context) -> CheckResult:
    """jñāpakaṁ owns continuity semantics; Safe Harbor only checks the
    interface is reachable and a store exists."""
    integration = REGISTRY["jnaapakam"]
    if not integration.is_configured(ctx):
        return CheckResult("continuity", NOT_CONFIGURED, "jnaapakam not configured")
    if not integration.db_path(ctx).is_file():
        return CheckResult("continuity", WARN, "no jnaapakam store yet")
    status = integration.status(ctx)
    return CheckResult("continuity", status.state, status.detail)


def validate_all(ctx: Context, *, backup: Path | None = None) -> list[CheckResult]:
    results: list[CheckResult] = [
        _separation_check(ctx),
        _pins_check(ctx),
        _generation_check(ctx),
        _structure_check(ctx),
        _backup_check(ctx, backup),
        _continuity_check(ctx),
    ]
    for name in ("restate", "jnaapakam", "hermes"):
        results.extend(REGISTRY[name].doctor(ctx))
    return results


def run(ctx: Context, *, backup: Path | None = None, machine_readable: bool = False) -> int:
    results = validate_all(ctx, backup=backup)
    if machine_readable:
        import json

        print(
            json.dumps(
                {
                    "overall": worst(results),
                    "checks": [
                        {"name": r.name, "state": r.state, "detail": r.detail}
                        for r in sorted_results(results)
                    ],
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        for r in sorted_results(results):
            print(r.render())
        print()
        print(f"Overall             {worst(results)}")
    return 0 if passed(results) else 1