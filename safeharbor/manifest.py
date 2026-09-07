"""Machine-readable manifest handling.

Safe Harbor manifests are plain JSON — transparent, inspectable with any
editor, and parseable without Safe Harbor itself. SHA-256 is used for every
hash. Nothing here requires an opaque or proprietary database.

Files produced/consumed:

    manifest/versions.lock     pinned component versions (JSON)
    manifest/artifacts.lock    acquired artifact records (JSON)
    manifest/checksums.sha256  sha256sum(1)-compatible flat checksum file
    generations/generation.json   environment/generation metadata
    <backup>/backup-manifest.json  backup contents + hashes
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import BACKUP_SCHEMA_VERSION, GEN1_GENERATION, __version__
from .checksums import sha256_file


class ManifestError(Exception):
    """Raised when a manifest is missing, malformed, or fails validation."""


# ---------------------------------------------------------------------------
# Low-level JSON helpers (atomic writes, so a failed run never corrupts a
# manifest that a previous run produced).
# ---------------------------------------------------------------------------


def write_json(path: Path | str, obj: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(obj, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def read_json(path: Path | str) -> Any:
    path = Path(path)
    if not path.is_file():
        raise ManifestError(f"missing manifest: {path}")
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except json.JSONDecodeError as exc:
        raise ManifestError(f"corrupt manifest {path}: {exc}") from exc


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# Checksums file (sha256sum-compatible: "<hex>  <path>")
# ---------------------------------------------------------------------------


def read_checksums(path: Path | str) -> dict[str, str]:
    """Return {relative_path: hex_sha256} from a sha256sum-style file."""
    out: dict[str, str] = {}
    path = Path(path)
    if not path.is_file():
        raise ManifestError(f"missing checksums file: {path}")
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                digest, _, rel = line.partition("  ")
                if not digest or not rel:
                    digest, _, rel = line.partition(" *")
            except ValueError:
                continue
            if digest and rel:
                out[rel.strip()] = digest.lower()
    return out


def write_checksums(path: Path | str, hashes: dict[str, str]) -> None:
    lines = "".join(f"{digest}  {rel}\n" for rel, digest in sorted(hashes.items()))
    write_json_path = Path(path)
    write_json_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=write_json_path.name + ".", dir=str(write_json_path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(lines)
        os.replace(tmp, write_json_path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# Version lock (manifest/versions.lock)
# ---------------------------------------------------------------------------

#: Required keys for every entry of the version lock, per the Safe Harbor
#: supply-chain manifest contract.
VERSION_ENTRY_KEYS = (
    "component",
    "version",
    "source_repository",
    "source_url",
    "release",
    "architecture",
)


def validate_version_lock(data: Any) -> None:
    if not isinstance(data, dict) or "components" not in data:
        raise ManifestError("versions.lock must contain a 'components' object")
    components = data["components"]
    if not isinstance(components, dict) or not components:
        raise ManifestError("versions.lock 'components' must be a non-empty object")
    for name, entry in components.items():
        if not isinstance(entry, dict):
            raise ManifestError(f"versions.lock entry {name!r} is not an object")
        for key in VERSION_ENTRY_KEYS:
            if key not in entry:
                raise ManifestError(f"versions.lock entry {name!r} missing key {key!r}")


def load_version_lock(path: Path | str) -> dict[str, Any]:
    data = read_json(path)
    validate_version_lock(data)
    return data


# ---------------------------------------------------------------------------
# Artifact lock (manifest/artifacts.lock)
# ---------------------------------------------------------------------------

ARTIFACT_ENTRY_KEYS = (
    "component",
    "version",
    "release",
    "artifact_filename",
    "architecture",
    "sha256",
    "acquisition_timestamp",
    "verification_status",
)


def validate_artifact_lock(data: Any) -> None:
    if not isinstance(data, dict) or "artifacts" not in data:
        raise ManifestError("artifacts.lock must contain an 'artifacts' list")
    artifacts = data["artifacts"]
    if not isinstance(artifacts, list) or not artifacts:
        raise ManifestError("artifacts.lock 'artifacts' must be a non-empty list")
    for entry in artifacts:
        if not isinstance(entry, dict):
            raise ManifestError("artifacts.lock contains a non-object entry")
        for key in ARTIFACT_ENTRY_KEYS:
            if key not in entry:
                raise ManifestError(f"artifacts.lock entry missing key {key!r}")


def load_artifact_lock(path: Path | str) -> dict[str, Any]:
    data = read_json(path)
    validate_artifact_lock(data)
    return data


# ---------------------------------------------------------------------------
# Generation / environment manifest
# ---------------------------------------------------------------------------


def build_generation_manifest(
    *,
    components: dict[str, dict[str, Any]],
    state_schema_version: str = "jnaapakam-protocol-0.5",
    a2a_enabled: bool = True,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the machine-readable generation manifest (see README, §25)."""
    manifest = {
        "safe_harbor_generation": GEN1_GENERATION,
        "manager": {"role": "manager", "architecture": _machine_arch()},
        "os": {"distribution": "ubuntu", "release": "26.04.1"},
        "components": components,
        "network": {"a2a_enabled": a2a_enabled},
        "state": {"schema_version": state_schema_version},
        "created_at": now_iso(),
        "created_by": f"safeharbor {__version__}",
    }
    if extra:
        manifest.update(extra)
    return manifest


def _machine_arch() -> str:
    import platform

    machine = platform.machine().lower()
    return {"x86_64": "amd64", "amd64": "amd64", "aarch64": "arm64"}.get(machine, machine)


def write_generation_manifest(layout: Any, manifest: dict[str, Any]) -> Path:
    """Persist a generation manifest under ``state/generations/``.

    The file is timestamped so an operator can inspect history; the newest
    file is also copied to ``generations/current.json`` for stable access.
    """
    stamp = now_iso().replace(":", "").replace("+", "Z").replace("-", "")
    path = layout.generations_dir / f"generation-{stamp}.json"
    write_json(path, manifest)
    current = layout.generations_dir / "current.json"
    write_json(current, manifest)
    return path


def load_current_generation(layout: Any) -> dict[str, Any] | None:
    path = layout.generations_dir / "current.json"
    if not path.is_file():
        return None
    return read_json(path)


def validate_generation_manifest(data: Any) -> None:
    if not isinstance(data, dict):
        raise ManifestError("generation manifest must be an object")
    for key in ("safe_harbor_generation", "components", "created_at"):
        if key not in data:
            raise ManifestError(f"generation manifest missing key {key!r}")
    if data["safe_harbor_generation"] != GEN1_GENERATION:
        raise ManifestError(
            f"generation manifest schema mismatch: "
            f"expected {GEN1_GENERATION}, got {data['safe_harbor_generation']}"
        )


# ---------------------------------------------------------------------------
# Backup manifest
# ---------------------------------------------------------------------------


@dataclass
class BackupEntry:
    """One backed-up file: relative location inside the backup + its hash."""

    relpath: str
    sha256: str
    size: int = 0


@dataclass
class BackupComponent:
    """How one component was backed up and what it contributed."""

    name: str
    strategy: str  # e.g. "quiesced_copy", "api_export", "metadata"
    entries: list[BackupEntry] = field(default_factory=list)


@dataclass
class BackupManifest:
    """Contents of a Safe Harbor backup, fully self-describing."""

    backup_id: str
    created_at: str
    created_by: str
    schema_version: int
    safe_harbor_generation: int
    components: dict[str, BackupComponent]
    generation_snapshot: dict[str, Any]
    reconstruction: dict[str, Any]
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "backup_id": self.backup_id,
            "created_at": self.created_at,
            "created_by": self.created_by,
            "schema_version": self.schema_version,
            "safe_harbor_generation": self.safe_harbor_generation,
            "components": {
                name: {
                    "strategy": comp.strategy,
                    "files": {e.relpath: {"sha256": e.sha256, "size": e.size} for e in comp.entries},
                }
                for name, comp in sorted(self.components.items())
            },
            "generation_snapshot": self.generation_snapshot,
            "reconstruction": self.reconstruction,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BackupManifest":
        components: dict[str, BackupComponent] = {}
        for name, comp in data.get("components", {}).items():
            entries = [
                BackupEntry(
                    relpath=rel,
                    sha256=meta["sha256"],
                    size=meta.get("size", 0),
                )
                for rel, meta in comp.get("files", {}).items()
            ]
            components[name] = BackupComponent(name=name, strategy=comp.get("strategy", "unknown"), entries=entries)
        return cls(
            backup_id=data["backup_id"],
            created_at=data.get("created_at", ""),
            created_by=data.get("created_by", ""),
            schema_version=data.get("schema_version", BACKUP_SCHEMA_VERSION),
            safe_harbor_generation=data.get("safe_harbor_generation", GEN1_GENERATION),
            components=components,
            generation_snapshot=data.get("generation_snapshot", {}),
            reconstruction=data.get("reconstruction", {}),
            notes=data.get("notes", []),
        )


def write_backup_manifest(backup_root: Path, manifest: BackupManifest) -> Path:
    path = backup_root / "backup-manifest.json"
    write_json(path, manifest.to_dict())
    return path


def read_backup_manifest(backup_root: Path | str) -> BackupManifest:
    path = Path(backup_root) / "backup-manifest.json"
    return BackupManifest.from_dict(read_json(path))


def validate_backup_manifest(
    backup_root: Path | str, *, strict: bool = True
) -> tuple[list[str], list[str]]:
    """Validate a backup on disk against its manifest.

    Returns (problems, warnings). Problems are fatal: a missing manifest,
    an unsupported schema, a listed file that is absent, or a hash mismatch.
    """
    backup_root = Path(backup_root)
    problems: list[str] = []
    warnings: list[str] = []

    manifest_path = backup_root / "backup-manifest.json"
    if not manifest_path.is_file():
        return [f"backup has no manifest: {backup_root}"], []

    try:
        manifest = read_backup_manifest(backup_root)
    except ManifestError as exc:
        return [f"unreadable backup manifest: {exc}"], []

    if manifest.schema_version != BACKUP_SCHEMA_VERSION:
        problems.append(
            f"unsupported backup schema_version {manifest.schema_version} "
            f"(this release supports {BACKUP_SCHEMA_VERSION})"
        )
        return problems, warnings

    if manifest.safe_harbor_generation != GEN1_GENERATION:
        warnings.append(
            f"backup safe_harbor_generation {manifest.safe_harbor_generation} "
            f"differs from current {GEN1_GENERATION}"
        )

    for name, comp in manifest.components.items():
        for entry in comp.entries:
            file_path = backup_root / entry.relpath
            if not file_path.is_file():
                problems.append(f"{name}: missing file {entry.relpath}")
                continue
            actual = sha256_file(file_path)
            if actual != entry.sha256:
                problems.append(f"{name}: hash mismatch {entry.relpath}")

    return problems, warnings


# Backward-compatible alias used by restore.py
def asdict_manifest(manifest: BackupManifest) -> dict[str, Any]:
    return manifest.to_dict()


def manifest_dict(manifest: BackupManifest) -> dict[str, Any]:
    return asdict(manifest)