"""Restate durable-execution integration (pinned: v1.7.2).

Verified facts (from the official v1.7.2 release and a local run of the
official musl x86_64 binary):

* binary: ``restate-server``; ``restate-server --version`` prints 1.7.2
* ``--base-dir`` defaults to ``restate-data`` under the CWD; Safe Harbor
  points it at ``/var/lib/safe-harbor/restate``
* node data lives at ``{base-dir}/{node-name}/`` containing ``db``,
  ``log-store``, ``replicated-metadata-server``, ``.cluster-marker``
  (observed locally)
* admin API on port 9070: ``GET /health`` returns 200 when healthy
  (observed locally); ingress on 8080; node-to-node on 5122
* Restate documents log-based consistency; a *consistent* single-node
  backup for Gen1 is a quiesced copy (service stopped while copying).
  Copying a live data directory is NOT a consistent backup.

REQUIRES_INTEGRATION_TEST: exercising ``restatectl``-driven backup tooling
on the Ubuntu target.
"""

from __future__ import annotations

import shutil
import stat
from pathlib import Path

from ..context import Context
from ..health import FAIL, NOT_CONFIGURED, OK, REQUIRES_TEST, WARN, CheckResult
from ..manifest import BackupComponent, BackupEntry
from .base import Integration

#: Default ports observed from the official binary.
ADMIN_PORT = 9070
INGRESS_PORT = 8080
NODE_NAME = "safeharbor-manager"
UNIT = "restate.service"

PINNED_VERSION = "v1.7.2"


class RestateIntegration(Integration):
    name = "restate"

    # -- paths ---------------------------------------------------------------

    def binary(self, ctx: Context) -> Path:
        return ctx.layout.restate_software_dir / "restate-server"

    def base_dir(self, ctx: Context) -> Path:
        return ctx.layout.restate_dir

    def data_dir(self, ctx: Context) -> Path:
        return self.base_dir(ctx) / NODE_NAME

    def health_url(self, ctx: Context) -> str:
        return f"http://127.0.0.1:{ADMIN_PORT}/health"

    # -- interface -----------------------------------------------------------

    def is_configured(self, ctx: Context) -> bool:
        return self.binary(ctx).is_file() or bool(
            ctx.service.is_active(UNIT)
        )

    def version(self, ctx: Context) -> str | None:
        binary = self.binary(ctx)
        if not binary.is_file():
            return None
        code, out = ctx.run_cmd([str(binary), "--version"], timeout=15)
        if code == 0:
            return out.strip().splitlines()[0] if out.strip() else "unknown"
        return None

    def status(self, ctx: Context) -> CheckResult:
        """Probe the real /health endpoint first — a live node that answers
        is semantic evidence even without a systemd unit."""
        active = ctx.service.is_active(UNIT)
        status, _ = ctx.http.get(self.health_url(ctx), timeout=3)
        if status == 200:
            detail = "/health 200"
            if active is None:
                detail += " (no systemd unit installed)"
            elif not active:
                detail += " (unit inactive but endpoint answers)"
            return self._check("restate", OK, detail)
        if active is None:
            return self._check("restate", NOT_CONFIGURED, "restate.service not installed")
        if not active:
            return self._check("restate", FAIL, "restate.service not active")
        return self._check("restate", FAIL, f"/health returned {status}")

    def doctor(self, ctx: Context) -> list[CheckResult]:
        results: list[CheckResult] = []
        results.append(self.status(ctx))

        binary = self.binary(ctx)
        if binary.is_file():
            ver = self.version(ctx)
            results.append(
                self._check("restate:binary", OK, ver or "unknown")
                if ver
                else self._check("restate:binary", FAIL, f"version probe failed: {binary}")
            )
        else:
            results.append(
                self._check(
                    "restate:binary",
                    NOT_CONFIGURED,
                    f"binary not installed at {binary}",
                )
            )

        data = self.data_dir(ctx)
        marker = data / ".cluster-marker"
        if data.is_dir():
            if marker.is_file():
                results.append(
                    self._check("restate:state", OK, f"data dir present at {data}")
                )
            else:
                results.append(
                    self._check(
                        "restate:state",
                        WARN,
                        f"data dir present but no {marker.name} found",
                    )
                )
        else:
            results.append(
                self._check("restate:state", NOT_CONFIGURED, f"no data dir at {data}")
            )

        results.append(
            self._check(
                "restate:backup",
                OK,
                "quiesced-copy strategy implemented; restatectl tooling REQUIRES_INTEGRATION_TEST",
            )
        )
        return results

    def backup(self, stage: Path, ctx: Context) -> BackupComponent:
        """Quiesced copy: stop the service, copy the data dir, start it again.

        This is the only Gen1 strategy that guarantees a consistent snapshot
        of Restate's log/db layout without relying on unverified tooling.
        """
        data = self.data_dir(ctx)
        if not data.is_dir():
            return BackupComponent(name=self.name, strategy="skipped")

        component = BackupComponent(name=self.name, strategy="quiesced_copy")
        if ctx.simulate:
            # Tests: record intent without touching services or files.
            component.entries.append(
                BackupEntry(relpath="restate/", sha256="simulated", size=0)
            )
            return component

        def _ignore_sockets(directory: str, names: list[str]) -> list[str]:
            """Restate leaves unix sockets (ingress/admin/fabric .sock) in the
            data dir — runtime artifacts, not durable state, and uncopyable."""
            return [n for n in names if stat.S_ISSOCK(Path(directory, n).stat().st_mode)]

        stop_needed = bool(ctx.service.is_active(UNIT))
        if stop_needed:
            ctx.service.stop(UNIT)
        try:
            dest = stage / "restate" / NODE_NAME
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(
                data, dest, dirs_exist_ok=True, symlinks=True, ignore=_ignore_sockets
            )
        finally:
            if stop_needed:
                ctx.service.start(UNIT)

        for path in sorted(dest.rglob("*")):
            if path.is_file():
                rel = str(path.relative_to(stage))
                component.entries.append(BackupEntry(relpath=rel, sha256="computed-later"))
        return component

    def restore(self, backup_root: Path, stage: Path, ctx: Context) -> None:
        data = self.data_dir(ctx)
        src = backup_root / "restate" / NODE_NAME
        if not src.is_dir():
            raise FileNotFoundError(f"backup contains no restate data: {src}")
        if ctx.simulate:
            return
        stop_needed = bool(ctx.service.is_active(UNIT))
        if stop_needed:
            ctx.service.stop(UNIT)
        try:
            if data.exists():
                shutil.rmtree(data)
            data.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(src, data, symlinks=True)
        finally:
            if stop_needed:
                ctx.service.start(UNIT)