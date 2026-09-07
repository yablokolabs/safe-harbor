"""`safeharbor doctor` — deeper validation of the whole environment.

Covers: supported OS/arch, filesystem, permissions, service status with real
endpoint probes, persistent-state availability, configuration validity,
integration connectivity, A2A peer, backup freshness and integrity,
environment manifest and generation metadata.

States: OK / WARN / FAIL / NOT_CONFIGURED / REQUIRES_TEST.
Exit code: 0 when nothing FAILs, 1 otherwise (for automation).
"""

from __future__ import annotations

import json
import os
import platform
import shutil
from pathlib import Path

from .context import Context
from .health import FAIL, NOT_CONFIGURED, OK, REQUIRES_TEST, WARN, CheckResult, passed, sorted_results, worst
from .integrations import REGISTRY
from .manifest import (
    load_artifact_lock,
    load_current_generation,
    load_version_lock,
    validate_generation_manifest,
    validate_backup_manifest,
)
from .paths import Layout


def _filesystem_check(ctx: Context) -> CheckResult:
    state = ctx.layout.state_dir
    try:
        state.mkdir(parents=True, exist_ok=True)
        probe = state / ".doctor-probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError as exc:
        return CheckResult("filesystem", FAIL, f"state dir not writable: {exc}")
    free = shutil.disk_usage(state)
    free_gb = free.free / (1024 ** 3)
    if free_gb < 2:
        return CheckResult(
            "filesystem", WARN, f"{state} writable but only {free_gb:.1f} GiB free"
        )
    return CheckResult("filesystem", OK, f"{state} writable ({free_gb:.1f} GiB free)")


def _permissions_check(ctx: Context) -> CheckResult:
    state = ctx.layout.state_dir
    if not state.is_dir():
        return CheckResult("permissions", NOT_CONFIGURED, f"{state} does not exist")
    mode = state.stat().st_mode & 0o777
    if mode & 0o002:
        return CheckResult("permissions", WARN, f"{state} is world-writable (mode {oct(mode)})")
    return CheckResult("permissions", OK, f"{state} mode {oct(mode)}")


def _config_check(ctx: Context) -> CheckResult:
    config = ctx.layout.config_dir
    if not config.is_dir():
        return CheckResult("config", NOT_CONFIGURED, f"no config dir at {config}")
    problems: list[str] = []
    for path in sorted(config.rglob("*.json")):
        try:
            with open(path, encoding="utf-8") as handle:
                json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            problems.append(f"{path.name}: {exc}")
    if problems:
        return CheckResult("config", FAIL, "; ".join(problems))
    return CheckResult("config", OK, f"config dir valid ({config})")


def _manifest_check(ctx: Context) -> CheckResult:
    """Lock manifests in the repo are the supply-chain source of truth."""
    checks: list[str] = []
    for rel in ("manifest/versions.lock", "manifest/artifacts.lock"):
        path = _repo_path() / rel
        if path.is_file():
            try:
                if "versions" in rel:
                    load_version_lock(path)
                else:
                    load_artifact_lock(path)
                checks.append(f"{rel} OK")
            except Exception as exc:  # ManifestError
                return CheckResult("manifest", FAIL, f"{rel}: {exc}")
        else:
            checks.append(f"{rel} missing")
    return CheckResult("manifest", OK, "; ".join(checks) if checks else "no manifests")


def _repo_path() -> Path:
    # The deploy copies the repo to /opt/safe-harbor/software/safe-harbor;
    # when running from a checkout, use the checkout.
    here = Path(__file__).resolve().parent.parent  # safeharbor/
    return here.parent  # repo root


def _generation_check(ctx: Context) -> CheckResult:
    generation = load_current_generation(ctx.layout)
    if generation is None:
        return CheckResult(
            "generation", WARN, "no generation manifest recorded (fresh environment?)"
        )
    try:
        validate_generation_manifest(generation)
    except Exception as exc:
        return CheckResult("generation", FAIL, str(exc))
    created = generation.get("created_at", "?")
    return CheckResult("generation", OK, f"generation manifest valid (created {created})")


def _backup_check(ctx: Context) -> CheckResult:
    backups = sorted(ctx.layout.backup_dir.glob("backup-*")) if ctx.layout.backup_dir.is_dir() else []
    if not backups:
        return CheckResult("backup", NOT_CONFIGURED, "no backups found")
    latest = backups[-1]
    problems, warnings = validate_backup_manifest(latest)
    if problems:
        return CheckResult("backup", FAIL, f"{latest.name}: {'; '.join(problems)}")
    if warnings:
        return CheckResult("backup", WARN, f"{latest.name}: {'; '.join(warnings)}")
    return CheckResult("backup", OK, f"latest backup valid: {latest.name}")


def _arch_check(ctx: Context) -> CheckResult:
    machine = platform.machine().lower()
    if machine in ("x86_64", "amd64"):
        return CheckResult("architecture", OK, f"{machine} (supported)")
    return CheckResult("architecture", WARN, f"{machine} (Gen1 targets amd64)")


def _security_check(ctx: Context) -> CheckResult:
    """A2A must never bind a public listener or require WAN access."""
    import socket

    findings: list[str] = []
    # Cheap probe: nothing should be listening on all interfaces on A2A ports
    # unless deliberately configured (config carries the explicit bind).
    config = ctx.layout.config_dir / "a2a"
    if config.is_dir():
        peers = config / "peers.json"
        if peers.is_file():
            try:
                data = json.loads(peers.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                return CheckResult("a2a-security", FAIL, "peers.json is corrupt")
            for peer in data.get("peers", []):
                host = peer.get("host", "")
                if host in ("0.0.0.0", "::"):
                    findings.append(f"peer {peer.get('name', '?')} binds wildcard")
            if findings:
                return CheckResult("a2a-security", FAIL, "; ".join(findings))
            return CheckResult("a2a-security", OK, "no wildcard binds in peer config")
    return CheckResult("a2a-security", NOT_CONFIGURED, "no A2A peer config")


def doctor_checks(ctx: Context) -> list[CheckResult]:
    results: list[CheckResult] = [
        _filesystem_check(ctx),
        _permissions_check(ctx),
        _arch_check(ctx),
        _config_check(ctx),
        _manifest_check(ctx),
        _generation_check(ctx),
        _backup_check(ctx),
        _security_check(ctx),
    ]

    for name in ("restate", "jnaapakam", "hermes"):
        integration = REGISTRY[name]
        results.extend(integration.doctor(ctx))

    return results


def run(ctx: Context, *, machine_readable: bool = False) -> int:
    results = doctor_checks(ctx)
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