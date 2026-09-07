"""`safeharbor backup` — consistent backup of persistent resident state.

Strategy per component comes from the integration adapters:

* Restate: quiesced copy (service stopped while the data dir is copied).
  A live-data copy is NOT a consistent Restate backup.
* jñāpakaṁ: official ``GET /backup`` JSON export when the server answers,
  else a quiesced copy of the SQLite store; soul files always captured.
* Hermes: quiesced copy of HERMES_HOME.

The flow is: stage into a hidden temp dir -> hash every staged file ->
write the backup manifest (which doubles as the integrity record) ->
atomically rename into place. A failed run leaves the previous backup
untouched.
"""

from __future__ import annotations

import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

from . import __version__
from .checksums import sha256_of_tree
from .context import Context
from .integrations import REGISTRY
from .manifest import (
    BackupComponent,
    BackupEntry,
    BackupManifest,
    build_generation_manifest,
    load_current_generation,
    now_iso,
    write_backup_manifest,
)


def _backup_id(backup_root: Path) -> str:
    """Timestamped backup id, made unique when two backups start in the
    same second (e.g. idempotent re-runs)."""
    base = "backup-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    candidate = base
    n = 1
    while (backup_root / candidate).exists():
        candidate = f"{base}-{n}"
        n += 1
    return candidate


def _collect_config(ctx: Context, stage: Path) -> BackupComponent:
    """Snapshot reconstruction-relevant configuration (no secrets).

    Copies the A2A peer config and per-component configs into the backup so
    a replacement machine can reconstruct the environment. Secret-bearing
    files (`.env`, anything world-readable only) are deliberately excluded;
    credentials are re-generated per deployment, never restored.
    """
    component = BackupComponent(name="reconstruction", strategy="metadata")
    config = ctx.layout.config_dir
    if not config.is_dir():
        return component
    dest = stage / "reconstruction" / "config"
    for path in sorted(config.rglob("*")):
        if path.is_file() and path.name not in (".env", "secrets.json"):
            rel = path.relative_to(config)
            target = dest / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            component.entries.append(
                BackupEntry(relpath=str(target.relative_to(stage)), sha256="computed-later")
            )
    return component


def run_backup(ctx: Context, *, note: str = "") -> int:
    backup_root = ctx.layout.backup_dir
    backup_id = _backup_id(backup_root)
    backup_root.mkdir(parents=True, exist_ok=True)
    stage = backup_root / f".staging-{backup_id}"
    final = backup_root / backup_id

    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True, exist_ok=True)

    components: dict[str, BackupComponent] = {}
    try:
        # 1. Stage every component's consistent snapshot.
        for name, integration in REGISTRY.items():
            components[name] = integration.backup(stage, ctx)

        components["reconstruction"] = _collect_config(ctx, stage)

        # 2. Generation snapshot: prefer the recorded one, else build fresh.
        generation = load_current_generation(ctx.layout)
        if generation is None:
            generation = build_generation_manifest(
                components={
                    name: {"version": integration.version(ctx) or "unknown"}
                    for name, integration in REGISTRY.items()
                }
            )

        # 3. Hash every staged file.
        hashes = sha256_of_tree(stage)

        # 4. Fill real hashes into the manifest entries.
        for component in components.values():
            filled: list[BackupEntry] = []
            for entry in component.entries:
                if entry.relpath.endswith("/"):
                    continue  # simulated dir marker from test mode
                digest = hashes.get(entry.relpath)
                if digest is None:
                    # Entry declared but file missing — a component bug;
                    # surface it instead of writing a silent hole.
                    raise RuntimeError(
                        f"{component.name}: staged entry missing {entry.relpath}"
                    )
                filled.append(
                    BackupEntry(relpath=entry.relpath, sha256=digest, size=(stage / entry.relpath).stat().st_size)
                )
            component.entries = filled

        manifest = BackupManifest(
            backup_id=backup_id,
            created_at=now_iso(),
            created_by=f"safeharbor {__version__}",
            schema_version=1,
            safe_harbor_generation=generation.get("safe_harbor_generation", 1),
            components=components,
            generation_snapshot=generation,
            reconstruction={"notes": [note] if note else [], "config_included": True},
            notes=[note] if note else [],
        )

        # 5. Write the manifest INSIDE the staged backup. The manifest is the
        #    integrity record; external verification re-hashes it directly
        #    (its own hash is not stored inside itself).
        write_backup_manifest(stage, manifest)

        # 6. Publish atomically.
        os.replace(stage, final)
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        raise

    print(f"Backup created: {final}")
    print(f"Manifest:       {final / 'backup-manifest.json'}")
    if ctx.simulate:
        print("(simulate mode — services and files were not touched)")
    return 0


def latest_backup(layout) -> Path | None:
    backups = sorted(layout.backup_dir.glob("backup-*")) if layout.backup_dir.is_dir() else []
    return backups[-1] if backups else None


def list_backups(ctx: Context) -> list[Path]:
    return sorted(ctx.layout.backup_dir.glob("backup-*")) if ctx.layout.backup_dir.is_dir() else []