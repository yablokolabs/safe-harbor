"""`safeharbor status` — fast operational summary.

Deliberately shallow: service active + real endpoint probe where cheap.
Deep validation belongs to `safeharbor doctor`. A process existing is never
treated as semantic health on its own.
"""

from __future__ import annotations

from .context import Context
from .health import CheckResult, passed, sorted_results, worst
from .integrations import REGISTRY
from .manifest import load_current_generation


def _manager_os_check(ctx: Context) -> CheckResult:
    """Gen1 manager target is Ubuntu Server LTS amd64. On the Debian build
    machine this is reported honestly (the manager check is not skipped)."""
    import platform

    try:
        with open("/etc/os-release", encoding="utf-8") as handle:
            content = handle.read()
    except OSError:
        return CheckResult(
            "manager_os", "FAIL", "/etc/os-release not readable"
        )

    fields: dict[str, str] = {}
    for line in content.splitlines():
        if "=" in line:
            key, _, value = line.partition("=")
            fields[key.strip()] = value.strip().strip('"')

    distro = fields.get("ID", "unknown")
    version = fields.get("VERSION_ID", "unknown")
    arch = platform.machine()

    if distro == "ubuntu" and version.startswith("26.04"):
        return CheckResult(
            "manager_os", "OK", f"{distro} {version} {arch}", evidence={"os": distro, "version": version}
        )

    # Any other Linux host (Debian build machine, other Ubuntu releases used
    # for development/CI, etc.) is reported honestly as WARN: the tool runs
    # and can validate, but this is not the Gen1 target. Strict OS rejection
    # belongs to the deploy-time gate (deploy/preflight.sh), not to a runtime
    # status check. FAIL is reserved for hosts that are not Linux at all or
    # whose OS cannot be determined.
    if distro == "debian":
        return CheckResult(
            "manager_os",
            "WARN",
            f"{distro} {version} {arch} — build/acquisition machine, not the Ubuntu Gen1 target",
            evidence={"os": distro, "version": version},
        )
    if distro != "unknown" and version != "unknown":
        return CheckResult(
            "manager_os",
            "WARN",
            f"{distro} {version} {arch} — Linux host, but not the Ubuntu 26.04 Gen1 target",
            evidence={"os": distro, "version": version},
        )
    return CheckResult(
        "manager_os",
        "FAIL",
        f"unsupported OS {distro} {version} {arch} (/etc/os-release unreadable or not Linux)",
    )


def _resident_check(ctx: Context) -> CheckResult:
    resident = ctx.layout.resident_dir
    if not resident.is_dir():
        return CheckResult("resident_state", "WARN", f"resident dir missing: {resident}")
    generation = load_current_generation(ctx.layout)
    detail = f"resident dir present at {resident}"
    if generation:
        detail += f"; generation recorded {generation.get('created_at', '?')}"
    else:
        detail += "; no generation manifest recorded yet"
    return CheckResult("resident_state", "OK", detail)


def _backup_freshness_check(ctx: Context) -> CheckResult:
    """Latest backup present? Old backups are a WARN, missing is a FAIL only
    when resident state exists (a fresh install has nothing to back up)."""
    backups = sorted(ctx.layout.backup_dir.glob("backup-*")) if ctx.layout.backup_dir.is_dir() else []
    if not backups:
        return CheckResult("backup", "NOT_CONFIGURED", "no backups found yet")
    latest = backups[-1]
    manifest = latest / "backup-manifest.json"
    if not manifest.is_file():
        return CheckResult("backup", "FAIL", f"latest backup has no manifest: {latest.name}")
    return CheckResult("backup", "OK", f"latest: {latest.name}")


def status_checks(ctx: Context) -> list[CheckResult]:
    results: list[CheckResult] = [_manager_os_check(ctx), _resident_check(ctx), _backup_freshness_check(ctx)]

    # A2A peer reachability (fast: one TCP/HTTP probe per configured peer).
    from .a2a import peer_reachability

    results.append(peer_reachability(ctx))

    # Every configured integration, in registry order.
    for name in ("restate", "jnaapakam", "hermes"):
        integration = REGISTRY[name]
        results.append(integration.status(ctx))

    return results


def run(ctx: Context, *, machine_readable: bool = False) -> int:
    results = status_checks(ctx)
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
        print("Safe Harbor Gen1")
        print()
        for r in sorted_results(results):
            print(r.render())
        print()
        print(f"Overall             {worst(results)}")
    return 0 if passed(results) else 1