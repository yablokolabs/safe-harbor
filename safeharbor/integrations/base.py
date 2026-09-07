"""The Integration interface.

A component adapter must be able to answer four questions about the upstream
software it wraps:

    is_configured()  — is this component part of this deployment at all?
    version()        — which pinned/installed version is present?
    status()         — fast operational summary (process/endpoint alive?)
    doctor()         — deep checks (real health endpoint, state availability)

and two operations:

    backup(stage)    — place a consistent snapshot into a staging dir
    restore(stage)   — put a backed-up snapshot back in place

Safe Harbor never reaches past this interface into upstream internals.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from ..context import Context
from ..health import CheckResult
from ..manifest import BackupComponent


class Integration(ABC):
    name: str = "integration"

    @abstractmethod
    def is_configured(self, ctx: Context) -> bool:
        """True when this component is deployed/enabled on this machine."""

    @abstractmethod
    def version(self, ctx: Context) -> str | None:
        """Installed version string, or None when not installed."""

    @abstractmethod
    def status(self, ctx: Context) -> CheckResult:
        """Fast status for `safeharbor status`."""

    @abstractmethod
    def doctor(self, ctx: Context) -> list[CheckResult]:
        """Deep checks for `safeharbor doctor`."""

    def backup(self, stage: Path, ctx: Context) -> BackupComponent:
        """Place a consistent snapshot under ``stage``; return what was done.

        Adapters that cannot run on this machine (no service present) should
        return a component with strategy ``"skipped"`` rather than fail the
        whole backup — a backup is still useful when it documents precisely
        what was and was not captured.
        """
        return BackupComponent(name=self.name, strategy="skipped")

    def restore(self, backup_root: Path, stage: Path, ctx: Context) -> None:
        """Restore this component from ``backup_root`` (via ``stage``).

        ``backup_root`` is the validated backup directory. Adapters restore
        through a temporary stage and move into place only when complete.
        """
        return None

    # -- shared helpers ------------------------------------------------------

    def _check(
        self, name: str, state: str, detail: str = "", **evidence: object
    ) -> CheckResult:
        return CheckResult(name=name, state=state, detail=detail, evidence=dict(evidence))