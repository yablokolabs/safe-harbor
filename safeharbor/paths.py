"""Gen1 filesystem layout.

The HARD separation enforced here is between SOFTWARE / ENVIRONMENT
(reproducible from a verified bundle) and PERSISTENT RESIDENT STATE
(portable, backed up, restored).

    /opt/safe-harbor/software/    reproducible software + integrations
    /etc/safe-harbor/             configuration (never resident identity)
    /var/lib/safe-harbor/         persistent resident state
    /var/log/safe-harbor/         logs
    /var/lib/safe-harbor/backups/ completed backups

Every path can be overridden through SH_* environment variables. Tests use
this to run the whole CLI against throwaway temporary directories, and a
deployment can relocate the tree without changing Safe Harbor code.

Uninstall MUST NOT delete the state tree by default; only an explicit
`purge` operation may do that.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _env(name: str, default: str) -> str:
    return os.environ.get(name, "").strip() or default


@dataclass(frozen=True)
class Layout:
    """Resolved Safe Harbor paths for the current machine."""

    software_dir: Path
    config_dir: Path
    state_dir: Path
    log_dir: Path
    backup_dir: Path

    # --- derived persistent-state locations ---------------------------------
    @property
    def resident_dir(self) -> Path:
        return self.state_dir / "resident"

    @property
    def hermes_dir(self) -> Path:
        """Hermes persistent agent data (HERMES_HOME target)."""
        return self.state_dir / "hermes"

    @property
    def jnaapakam_dir(self) -> Path:
        """jñāpakaṁ SQLite store + soul files."""
        return self.state_dir / "jnaapakam"

    @property
    def restate_dir(self) -> Path:
        """Restate durable-execution data (--base-dir target)."""
        return self.state_dir / "restate"

    @property
    def projects_dir(self) -> Path:
        return self.state_dir / "projects"

    @property
    def generations_dir(self) -> Path:
        return self.state_dir / "generations"

    # --- derived software locations -----------------------------------------
    @property
    def hermes_software_dir(self) -> Path:
        return self.software_dir / "hermes"

    @property
    def jnaapakam_software_dir(self) -> Path:
        return self.software_dir / "jnaapakam"

    @property
    def restate_software_dir(self) -> Path:
        return self.software_dir / "restate"

    @property
    def bin_dir(self) -> Path:
        return self.software_dir / "bin"

    def create_state_dirs(self) -> None:
        """Create the persistent-state directory tree (idempotent)."""
        for d in (
            self.resident_dir,
            self.hermes_dir,
            self.jnaapakam_dir,
            self.restate_dir,
            self.projects_dir,
            self.generations_dir,
            self.backup_dir,
            self.log_dir,
        ):
            d.mkdir(parents=True, exist_ok=True)


def default_layout() -> Layout:
    """Resolve the layout from the environment (or production defaults)."""
    return Layout(
        software_dir=Path(_env("SH_SOFTWARE_DIR", "/opt/safe-harbor/software")),
        config_dir=Path(_env("SH_CONFIG_DIR", "/etc/safe-harbor")),
        state_dir=Path(_env("SH_STATE_DIR", "/var/lib/safe-harbor")),
        log_dir=Path(_env("SH_LOG_DIR", "/var/log/safe-harbor")),
        backup_dir=Path(_env("SH_BACKUP_DIR", "/var/lib/safe-harbor/backups")),
    )