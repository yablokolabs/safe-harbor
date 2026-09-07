"""`safeharbor restore` — validated, deliberate reconstruction.

Restore is a separate operation from software rollback (see ROLLBACK.md).
It is destructive by nature and therefore requires:

    1. a readable, schema-compatible backup with a valid manifest;
    2. every listed file present and matching its SHA-256;
    3. no silently-newer resident state that would be overwritten
       (refused unless --force);
    4. explicit operator confirmation (--yes) or an interactive prompt.

``--dry-run`` performs steps 1-3 and prints the intended changes without
touching anything.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .context import Context
from .integrations import REGISTRY
from .manifest import (
    ManifestError,
    load_current_generation,
    now_iso,
    read_backup_manifest,
    validate_backup_manifest,
    write_generation_manifest,
)


@dataclass
class RestorePlan:
    backup_id: str
    created_at: str
    components: list[str]
    files: list[str]
    total_bytes: int
    problems: list[str]
    warnings: list[str]
    conflicts: list[str]

    @property
    def ok(self) -> bool:
        return not self.problems and not self.conflicts


def _conflicts(backup_manifest, current_generation) -> list[str]:
    """Detect 'newer state would be overwritten' situations."""
    conflicts: list[str] = []
    if backup_manifest is None or current_generation is None:
        return conflicts
    backup_created = backup_manifest.created_at
    current_created = current_generation.get("created_at", "")
    # Compare ISO timestamps lexicographically (UTC, same format).
    if backup_created and current_created and current_created > backup_created:
        conflicts.append(
            f"current environment recorded at {current_created} is NEWER than "
            f"this backup ({backup_created}); restoring would discard newer state"
        )
    return conflicts


def plan_restore(backup_root: Path, ctx: Context, *, force: bool = False) -> RestorePlan:
    problems, warnings = validate_backup_manifest(backup_root)

    try:
        manifest = read_backup_manifest(backup_root)
    except ManifestError as exc:
        return RestorePlan(
            backup_id=backup_root.name, created_at="", components=[], files=[],
            total_bytes=0, problems=[str(exc)], warnings=[], conflicts=[],
        )

    files: list[str] = []
    total = 0
    for name, comp in manifest.components.items():
        for entry in comp.entries:
            files.append(entry.relpath)
            total += entry.size

    conflicts = _conflicts(manifest, load_current_generation(ctx.layout)) if not force else []

    return RestorePlan(
        backup_id=manifest.backup_id,
        created_at=manifest.created_at,
        components=sorted(manifest.components.keys()),
        files=sorted(files),
        total_bytes=total,
        problems=problems,
        warnings=warnings,
        conflicts=conflicts,
    )


def render_plan(plan: RestorePlan) -> str:
    lines = [
        f"Backup:            {plan.backup_id}",
        f"Created:           {plan.created_at}",
        f"Components:        {', '.join(plan.components) or '(none)'}",
        f"Files:             {len(plan.files)}",
        f"Total size:        {plan.total_bytes} bytes",
    ]
    for problem in plan.problems:
        lines.append(f"PROBLEM: {problem}")
    for warning in plan.warnings:
        lines.append(f"WARNING: {warning}")
    for conflict in plan.conflicts:
        lines.append(f"CONFLICT: {conflict}")
    return "\n".join(lines)


def dry_run(backup_root: Path, ctx: Context, *, force: bool = False) -> int:
    plan = plan_restore(backup_root, ctx, force=force)
    print(render_plan(plan))
    if plan.problems or plan.conflicts:
        print()
        print("Restore REFUSED — fix the problems above (or use --force only for conflicts).")
        return 1
    print()
    print("Restore would proceed: files above would replace current resident state.")
    return 0


def perform_restore(backup_root: Path, ctx: Context, *, force: bool = False) -> int:
    plan = plan_restore(backup_root, ctx, force=force)
    print(render_plan(plan))

    if plan.problems:
        print()
        print("Restore REFUSED — backup is corrupt or incomplete.")
        return 1
    if plan.conflicts:
        print()
        print("Restore REFUSED — newer resident state would be overwritten (--force overrides).")
        return 1

    # Restore each component through its adapter.
    for name, integration in REGISTRY.items():
        try:
            integration.restore(backup_root, backup_root, ctx)
            print(f"restored: {name}")
        except FileNotFoundError as exc:
            print(f"skipped:   {name} ({exc})")
        except Exception as exc:  # noqa: BLE001 — report and continue
            print(f"FAILED:    {name} ({exc})")
            return 1

    # Record a fresh environment manifest so continuity metadata reflects
    # the reconstruction event.
    generation = load_current_generation(ctx.layout) or {}
    generation["created_at"] = now_iso()
    generation["notes"] = generation.get("notes", []) + [
        f"restored from backup {plan.backup_id} on {now_iso()}"
    ]
    path = write_generation_manifest(ctx.layout, generation)
    print(f"recorded reconstruction generation: {path}")
    print()
    print("Restore complete. Run `safeharbor doctor` to validate continuity.")
    return 0


def run(backup_root: Path, ctx: Context, *, dry: bool = False, force: bool = False, yes: bool = False) -> int:
    if dry:
        return dry_run(backup_root, ctx, force=force)
    if not yes:
        answer = input(
            "Type YES to overwrite current resident state with this backup: "
        ).strip()
        if answer != "YES":
            print("Aborted — no changes made.")
            return 1
    return perform_restore(backup_root, ctx, force=force)