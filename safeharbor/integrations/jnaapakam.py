"""jñāpakaṁ continuity integration (pinned: commit 7fa08bb, release 0.5.1).

Verified facts (from the pinned commit's README, PROTOCOL.md, pyproject and
CLI source):

* pip package ``jnaapakam`` 0.5.1; only runtime dependency is aiohttp
* ``jnaapakam serve`` binds 127.0.0.1:8889 by default
* env: MEMORY_HOST, MEMORY_PORT/PORT, MEMORY_DB, MEMORY_AUTH_TOKEN,
  MEMORY_MODEL, MEMORY_SIGNING_KEY (Ed25519 seals)
* health: ``GET /status`` returns JSON statistics
* backup/restore: ``GET /backup`` exports memories+consolidations as JSON;
  ``POST /restore`` imports it
* identity: ``GET /agent``; generations: ``/generations`` (list/create/
  validate/promote/rollback)
* SQLite FTS5 store; no daemon, no network call on first start
* safe bind rule: a non-loopback bind REQUIRES MEMORY_AUTH_TOKEN

Safe Harbor keeps the jñāpakaṁ store under the persistent-state tree
(``/var/lib/safe-harbor/jnaapakam/``) and the agent soul files
(SOUL.md/IDENTITY.md/MEMORY.md) under ``resident/``. Backup uses the
official ``/backup`` API when the server is reachable, falling back to a
quiesced copy of the SQLite file when it is not.
"""

from __future__ import annotations

import json
import shutil
import urllib.request
from pathlib import Path

from ..context import Context
from ..health import FAIL, NOT_CONFIGURED, OK, WARN, CheckResult
from ..manifest import BackupComponent, BackupEntry
from .base import Integration

#: Default loopback bind observed from upstream source.
HOST = "127.0.0.1"
PORT = 8889
UNIT = "jnaapakam.service"
DB_FILENAME = "memory.db"

PINNED_RELEASE = "0.5.1"
PINNED_COMMIT = "7fa08bb8b4204ea70642d2c11d671afa91fb34e7"

#: Soul files created by `jnaapakam init`; treated as resident identity data.
SOUL_FILES = ("SOUL.md", "IDENTITY.md", "MEMORY.md")


class JnaapakamIntegration(Integration):
    name = "jnaapakam"

    # -- paths ---------------------------------------------------------------

    def binary(self, ctx: Context) -> Path:
        return ctx.layout.jnaapakam_software_dir / "venv" / "bin" / "jnaapakam"

    def db_path(self, ctx: Context) -> Path:
        return ctx.layout.jnaapakam_dir / DB_FILENAME

    def resident_dir(self, ctx: Context) -> Path:
        return ctx.layout.resident_dir

    def base_url(self) -> str:
        return f"http://{HOST}:{PORT}"

    # -- interface -----------------------------------------------------------

    def is_configured(self, ctx: Context) -> bool:
        return self.binary(ctx).is_file() or bool(ctx.service.is_active(UNIT))

    def version(self, ctx: Context) -> str | None:
        binary = self.binary(ctx)
        if not binary.is_file():
            return None
        code, out = ctx.run_cmd([str(binary), "--version"], timeout=15)
        if code == 0:
            return out.strip().splitlines()[0] if out.strip() else "unknown"
        return None

    def status(self, ctx: Context) -> CheckResult:
        """Probe the real /status endpoint first — a live store that answers
        is semantic evidence, even when it runs without a systemd unit (e.g.
        a manually started instance).
        """
        active = ctx.service.is_active(UNIT)
        status, body = ctx.http.get(f"{self.base_url()}/status", timeout=3)
        if status == 200:
            detail = "/status 200"
            if isinstance(body, dict) and "total_memories" in body:
                detail += f" ({body.get('total_memories')} memories)"
            if active is None:
                detail += " (no systemd unit installed)"
            elif not active:
                detail += " (unit inactive but endpoint answers)"
            return self._check("jnaapakam", OK, detail)
        if active is None:
            return self._check("jnaapakam", NOT_CONFIGURED, "jnaapakam.service not installed")
        if not active:
            return self._check("jnaapakam", FAIL, "jnaapakam.service not active")
        return self._check("jnaapakam", FAIL, f"/status returned {status}")

    def doctor(self, ctx: Context) -> list[CheckResult]:
        results: list[CheckResult] = [self.status(ctx)]

        binary = self.binary(ctx)
        if binary.is_file():
            ver = self.version(ctx)
            results.append(
                self._check("jnaapakam:binary", OK, ver or "unknown")
                if ver
                else self._check("jnaapakam:binary", FAIL, f"version probe failed: {binary}")
            )
        else:
            results.append(
                self._check(
                    "jnaapakam:binary",
                    NOT_CONFIGURED,
                    f"binary not installed at {binary}",
                )
            )

        db = self.db_path(ctx)
        if db.is_file():
            size_kb = db.stat().st_size // 1024
            results.append(
                self._check("jnaapakam:state", OK, f"store present ({size_kb} KiB)")
            )
        else:
            results.append(
                self._check("jnaapakam:state", WARN, f"no store yet at {db} (fresh install)")
            )

        soul = self.resident_dir(ctx)
        present = [f for f in SOUL_FILES if (soul / f).is_file()]
        if present:
            results.append(
                self._check(
                    "jnaapakam:soul",
                    OK,
                    f"resident soul files: {', '.join(present)}",
                )
            )
        else:
            results.append(
                self._check(
                    "jnaapakam:soul",
                    WARN,
                    "no soul files (SOUL.md/IDENTITY.md/MEMORY.md) in resident dir",
                )
            )
        return results

    def backup(self, stage: Path, ctx: Context) -> BackupComponent:
        """Prefer the official /backup JSON export; fall back to a quiesced
        copy of the SQLite store. Soul files always come from resident/."""
        component = BackupComponent(name=self.name, strategy="api_export")
        dest = stage / "jnaapakam"
        dest.mkdir(parents=True, exist_ok=True)

        # 1. Soul files (resident identity — always captured).
        for name in SOUL_FILES:
            src = self.resident_dir(ctx) / name
            if src.is_file():
                shutil.copy2(src, dest / name)
                component.entries.append(
                    BackupEntry(relpath=f"jnaapakam/{name}", sha256="computed-later")
                )

        # 2. Memory store: API export when the server answers.
        if not ctx.simulate:
            status, body = ctx.http.get(f"{self.base_url()}/backup", timeout=10)
            if status == 200:
                export_path = dest / "export.json"
                export_path.write_text(
                    json.dumps(body, indent=2, sort_keys=True) if not isinstance(body, str) else body,
                    encoding="utf-8",
                )
                component.entries.append(
                    BackupEntry(relpath="jnaapakam/export.json", sha256="computed-later")
                )
                component.strategy = "api_export"
                return component

        # 3. Fallback: quiesced copy of the SQLite store.
        db = self.db_path(ctx)
        if db.is_file():
            component.strategy = "quiesced_copy"
            if ctx.simulate:
                component.entries.append(
                    BackupEntry(relpath="jnaapakam/memory.db", sha256="simulated")
                )
                return component
            stop_needed = bool(ctx.service.is_active(UNIT))
            if stop_needed:
                ctx.service.stop(UNIT)
            try:
                shutil.copy2(db, dest / DB_FILENAME)
            finally:
                if stop_needed:
                    ctx.service.start(UNIT)
            component.entries.append(
                BackupEntry(relpath=f"jnaapakam/{DB_FILENAME}", sha256="computed-later")
            )
        elif not component.entries:
            component.strategy = "skipped"
        return component

    def restore(self, backup_root: Path, stage: Path, ctx: Context) -> None:
        src = backup_root / "jnaapakam"
        if not src.is_dir():
            raise FileNotFoundError(f"backup contains no jnaapakam data: {src}")

        # Soul files back into resident state.
        resident = self.resident_dir(ctx)
        resident.mkdir(parents=True, exist_ok=True)
        for name in SOUL_FILES:
            soul_src = src / name
            if soul_src.is_file():
                shutil.copy2(soul_src, resident / name)

        # Store: prefer the SQLite file, else re-import the JSON export.
        db_src = src / DB_FILENAME
        if db_src.is_file():
            if ctx.simulate:
                return
            db = self.db_path(ctx)
            stop_needed = bool(ctx.service.is_active(UNIT))
            if stop_needed:
                ctx.service.stop(UNIT)
            try:
                db.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(db_src, db)
            finally:
                if stop_needed:
                    ctx.service.start(UNIT)
        else:
            export_src = src / "export.json"
            if not export_src.is_file():
                raise FileNotFoundError(
                    f"backup jnaapakam has neither {DB_FILENAME} nor export.json"
                )
            # Import via the official API on a running server (live migration).
            if ctx.simulate:
                return
            payload = export_src.read_text(encoding="utf-8")
            request = urllib.request.Request(
                f"{self.base_url()}/restore",
                data=payload.encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=60) as resp:
                if resp.status != 200:
                    raise RuntimeError(f"/restore returned {resp.status}")