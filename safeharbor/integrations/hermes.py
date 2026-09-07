"""Hermes Agent integration (pinned: v0.21.0, git tag v2026.8.31).

Verified facts (from the pinned tag's source):

* Python project, MIT license, installed via the official installer
  (curl|bash — which Safe Harbor does NOT use on targets; the offline
  bundle vendors the verified source + uv instead)
* ``HERMES_HOME`` environment variable relocates all Hermes data
  (hermes_cli/_startup_fast.py); Safe Harbor sets it to the persistent
  state tree
* ``hermes --version`` prints the version; ``hermes doctor`` is the
  upstream deep-check command
* A2A: plugin platform ``plugins/platforms/a2a/``; default port 9900;
  Agent Card at ``/.well-known/agent-card.json``; JSON-RPC ``message/send``;
  auth via ``A2A_BEARER_TOKEN`` / ``A2A_PEER_TOKENS`` (per-peer) /
  ``A2A_TRUSTED_PEERS`` allow-list; bind refuses non-loopback unless a
  token is configured; audit log at ``$HERMES_HOME/a2a_audit.jsonl``

REQUIRES_INTEGRATION_TEST: the exact gateway/A2A enablement steps on the
Ubuntu manager and Windows specialist.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from ..context import Context
from ..health import FAIL, NOT_CONFIGURED, OK, REQUIRES_TEST, WARN, CheckResult
from ..manifest import BackupComponent, BackupEntry
from .base import Integration

UNIT = "hermes-manager.service"
PINNED_VERSION = "v0.21.0"
PINNED_TAG = "v2026.8.31"

#: Default A2A port from plugins/platforms/a2a/adapter.py.
A2A_PORT = 9900


class HermesIntegration(Integration):
    name = "hermes"

    # -- paths ---------------------------------------------------------------

    def home_dir(self, ctx: Context) -> Path:
        """HERMES_HOME target — Hermes persistent agent data."""
        return ctx.layout.hermes_dir

    def binary(self, ctx: Context) -> Path:
        # Hermes installs its launcher under HERMES_HOME/bin.
        return self.home_dir(ctx) / "bin" / "hermes"

    def a2a_audit_path(self, ctx: Context) -> Path:
        return self.home_dir(ctx) / "a2a_audit.jsonl"

    # -- interface -----------------------------------------------------------

    def is_configured(self, ctx: Context) -> bool:
        return self.binary(ctx).is_file() or bool(ctx.service.is_active(UNIT))

    def version(self, ctx: Context) -> str | None:
        binary = self.binary(ctx)
        if not binary.is_file():
            return None
        code, out = ctx.run_cmd([str(binary), "--version"], timeout=20)
        if code == 0:
            return out.strip().splitlines()[0] if out.strip() else "unknown"
        return None

    def status(self, ctx: Context) -> CheckResult:
        active = ctx.service.is_active(UNIT)
        if active is None:
            return self._check("hermes", NOT_CONFIGURED, "hermes-manager.service not installed")
        if not active:
            return self._check("hermes", FAIL, "hermes-manager.service not active")
        ver = self.version(ctx)
        detail = "service active"
        if ver:
            detail += f" ({ver})"
        return self._check("hermes", OK, detail)

    def doctor(self, ctx: Context) -> list[CheckResult]:
        results: list[CheckResult] = [self.status(ctx)]

        home = self.home_dir(ctx)
        if home.is_dir():
            results.append(self._check("hermes:home", OK, str(home)))
        else:
            results.append(
                self._check("hermes:home", NOT_CONFIGURED, f"no HERMES_HOME at {home}")
            )

        binary = self.binary(ctx)
        if binary.is_file():
            ver = self.version(ctx)
            results.append(
                self._check("hermes:binary", OK, ver or "unknown")
                if ver
                else self._check("hermes:binary", FAIL, f"version probe failed: {binary}")
            )
        else:
            results.append(
                self._check(
                    "hermes:binary",
                    NOT_CONFIGURED,
                    f"hermes launcher not found at {binary}",
                )
            )

        audit = self.a2a_audit_path(ctx)
        if audit.is_file():
            results.append(
                self._check("hermes:a2a-audit", OK, f"audit log present ({audit.name})")
            )
        else:
            results.append(
                self._check(
                    "hermes:a2a-audit",
                    REQUIRES_TEST,
                    "a2a_audit.jsonl not present yet — appears after first A2A exchange",
                )
            )

        results.append(
            self._check(
                "hermes:deep-doctor",
                REQUIRES_TEST,
                "`hermes doctor` requires the configured Ubuntu manager (REQUIRES_INTEGRATION_TEST)",
            )
        )
        return results

    def backup(self, stage: Path, ctx: Context) -> BackupComponent:
        """Quiesced copy of HERMES_HOME (agent data: config, history, skills).

        Hermes' persistent data is one directory tree; copying it while the
        gateway is stopped is consistent. Copying a live tree is not.
        """
        home = self.home_dir(ctx)
        if not home.is_dir():
            return BackupComponent(name=self.name, strategy="skipped")

        component = BackupComponent(name=self.name, strategy="quiesced_copy")
        if ctx.simulate:
            component.entries.append(
                BackupEntry(relpath="hermes/", sha256="simulated", size=0)
            )
            return component

        stop_needed = bool(ctx.service.is_active(UNIT))
        if stop_needed:
            ctx.service.stop(UNIT)
        try:
            dest = stage / "hermes"
            dest.mkdir(parents=True, exist_ok=True)
            shutil.copytree(home, dest, dirs_exist_ok=True, symlinks=True)
        finally:
            if stop_needed:
                ctx.service.start(UNIT)

        for path in sorted(dest.rglob("*")):
            if path.is_file():
                component.entries.append(
                    BackupEntry(relpath=str(path.relative_to(stage)), sha256="computed-later")
                )
        return component

    def restore(self, backup_root: Path, stage: Path, ctx: Context) -> None:
        src = backup_root / "hermes"
        if not src.is_dir():
            raise FileNotFoundError(f"backup contains no hermes data: {src}")
        if ctx.simulate:
            return
        home = self.home_dir(ctx)
        stop_needed = bool(ctx.service.is_active(UNIT))
        if stop_needed:
            ctx.service.stop(UNIT)
        try:
            if home.exists():
                shutil.rmtree(home)
            home.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(src, home, symlinks=True)
        finally:
            if stop_needed:
                ctx.service.start(UNIT)