"""Shared fixtures.

Every test runs against throwaway temporary directories with simulate=True,
so nothing in the suite can touch real services, real network, or real
system paths. Tests MUST NOT damage the development machine.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from safeharbor.context import Context  # noqa: E402
from safeharbor.paths import Layout  # noqa: E402


@pytest.fixture
def tmp_layout(tmp_path: Path) -> Layout:
    layout = Layout(
        software_dir=tmp_path / "software",
        config_dir=tmp_path / "etc",
        state_dir=tmp_path / "var" / "lib",
        log_dir=tmp_path / "var" / "log",
        backup_dir=tmp_path / "var" / "lib" / "backups",
    )
    layout.create_state_dirs()
    return layout


@pytest.fixture
def ctx(tmp_layout: Layout) -> Context:
    return Context(layout=tmp_layout, simulate=True)


@pytest.fixture
def peers_config(tmp_layout: Layout) -> Path:
    """Write a peers.json with one fake specialist peer."""
    config = tmp_layout.config_dir / "a2a"
    config.mkdir(parents=True, exist_ok=True)
    path = config / "peers.json"
    path.write_text(
        json.dumps(
            {
                "peers": [
                    {
                        "name": "specialist-node",
                        "role": "specialist",
                        "host": "127.0.0.1",
                        "port": 9900,
                        "token_env": "A2A_TOKEN_SPECIALIST",
                        "approved_capabilities": ["get-local-time"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return path