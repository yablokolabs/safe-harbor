"""Live adapter integration tests.

These start the REAL pinned upstream components on a throwaway temp dir
and exercise the Safe Harbor adapters against them (endpoint probes and
backup staging). They auto-skip when the upstream binaries are not
available on the machine, so the standard suite stays runnable anywhere.

They never touch systemd, never use real system paths, and kill the
components they start. Component startup is polled (health endpoint) up
to a deadline because first boot can take tens of seconds.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

from safeharbor.context import Context
from safeharbor.integrations import REGISTRY
from safeharbor.paths import Layout

# Location overrides for the upstream binaries (dev machines vary).
RESTATE_BIN = Path(os.environ.get(
    "SH_TEST_RESTATE_BIN",
    "/home/box/upstream/restate/restate-server-x86_64-unknown-linux-musl/restate-server",
))
JNAAPAKAM_BIN = Path(os.environ.get(
    "SH_TEST_JNAAPAKAM_BIN",
    "/tmp/jn-test/bin/jnaapakam",
))

restate_available = pytest.mark.skipif(
    not RESTATE_BIN.is_file(), reason="restate-server binary not available"
)
jnaapakam_available = pytest.mark.skipif(
    not JNAAPAKAM_BIN.is_file(), reason="jnaapakam binary not available"
)


def _layout(tmp_path: Path) -> Layout:
    layout = Layout(
        software_dir=tmp_path / "software",
        config_dir=tmp_path / "etc",
        state_dir=tmp_path / "var" / "lib",
        log_dir=tmp_path / "var" / "log",
        backup_dir=tmp_path / "var" / "lib" / "backups",
    )
    layout.create_state_dirs()
    return layout


@restate_available
def test_restate_live_health_and_backup(tmp_path):
    """Start the real Restate server and check /health + quiesced backup.

    Restate binds unix sockets whose path must fit SUN_LEN (~107 chars),
    so the server runs from a SHORT base dir under /tmp instead of pytest's
    long tmp_path.
    """
    base = Path(f"/tmp/sh-restate-{os.getpid()}")
    if base.exists():
        shutil.rmtree(base)
    layout = Layout(
        software_dir=base / "software",
        config_dir=base / "etc",
        state_dir=base / "var" / "lib",
        log_dir=base / "var" / "log",
        backup_dir=base / "var" / "lib" / "backups",
    )
    layout.create_state_dirs()
    log_path = tmp_path / "restate-server.log"
    with open(log_path, "wb") as log:
        server = subprocess.Popen(
            [
                str(RESTATE_BIN),
                "--base-dir",
                str(layout.restate_dir),
                "--node-name",
                "safeharbor-manager",
                "--no-logo",
            ],
            stdout=log,
            stderr=subprocess.STDOUT,
        )
    try:
        ctx = Context(layout=layout, simulate=False)
        result = REGISTRY["restate"].status(ctx)
        deadline = time.time() + 60
        while result.state != "OK" and time.time() < deadline:
            time.sleep(2)
            result = REGISTRY["restate"].status(ctx)
        assert result.state == "OK", (
            f"{result.detail}; server log tail: "
            f"{log_path.read_text(encoding='utf-8', errors='replace')[-1500:]}"
        )

        stage = tmp_path / "stage"
        stage.mkdir()
        component = REGISTRY["restate"].backup(stage, ctx)
        assert component.strategy == "quiesced_copy"
        rels = [e.relpath for e in component.entries]
        assert rels, "quiesced copy produced no files"
        assert not any(".sock" in r for r in rels), "unix sockets must be excluded"
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
        shutil.rmtree(base, ignore_errors=True)


@jnaapakam_available
def test_jnaapakam_live_status_and_api_export(tmp_path):
    """Start the real jñāpakaṁ server and check /status + /backup export."""
    layout = _layout(tmp_path)
    log_path = tmp_path / "jnaapakam-server.log"
    with open(log_path, "wb") as log:
        server = subprocess.Popen(
            [
                str(JNAAPAKAM_BIN),
                "serve",
                "--host",
                "127.0.0.1",
                "--port",
                "8893",
                "--db",
                str(layout.jnaapakam_dir / "memory.db"),
            ],
            stdout=log,
            stderr=subprocess.STDOUT,
        )
    import safeharbor.integrations.jnaapakam as jn

    original_port = jn.PORT
    jn.PORT = 8893
    try:
        ctx = Context(layout=layout, simulate=False)
        result = REGISTRY["jnaapakam"].status(ctx)
        deadline = time.time() + 30
        while result.state != "OK" and time.time() < deadline:
            time.sleep(1)
            result = REGISTRY["jnaapakam"].status(ctx)
        assert result.state == "OK", (
            f"{result.detail}; server log tail: "
            f"{log_path.read_text(encoding='utf-8', errors='replace')[-1500:]}"
        )

        stage = tmp_path / "stage"
        stage.mkdir()
        component = REGISTRY["jnaapakam"].backup(stage, ctx)
        assert component.strategy == "api_export"
        export = stage / "jnaapakam" / "export.json"
        assert export.is_file()
        data = json.loads(export.read_text(encoding="utf-8"))
        assert "agent_id" in data, "official /backup export must carry agent identity"
    finally:
        jn.PORT = original_port
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()