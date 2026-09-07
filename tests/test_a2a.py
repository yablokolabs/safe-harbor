"""A2A harness: level behavior with simulated plumbing."""

from __future__ import annotations

import json
import os

from safeharbor.context import Context, HttpClient, ServiceControl
from safeharbor.a2a import run_test, load_peers, level1_network, Peer


def _ctx(tmp_layout, peers_config, *, fake_http=None, probe=None):
    ctx = Context(
        layout=tmp_layout,
        simulate=True,
        service=ServiceControl(simulate=True),
        http=HttpClient(simulate=True, fake_responses=fake_http or {}),
    )
    if probe:
        ctx.socket_probe = probe
    return ctx


def test_level1_fails_when_peer_unreachable(tmp_layout, peers_config):
    ctx = _ctx(tmp_layout, peers_config, probe=lambda peer: (-1, "refused"))
    peer = load_peers(ctx)[0]
    result = level1_network(ctx, peer)
    assert result.state == "FAIL"


def test_level1_passes_when_reachable(tmp_layout, peers_config):
    ctx = _ctx(tmp_layout, peers_config, probe=lambda peer: (0, "connected"))
    peer = load_peers(ctx)[0]
    result = level1_network(ctx, peer)
    assert result.state == "OK"


def test_full_harness_pass(tmp_layout, peers_config, capsys):
    url = "http://127.0.0.1:9900"
    fake_http = {
        f"{url}/.well-known/agent-card.json": (
            200,
            {"name": "specialist-node", "url": url, "supportedInterfaces": ["a2a.v1"]},
        ),
        f"{url}/": (200, {"__echo__": True}),
    }
    # audit log with the deterministic simulate task ids
    audit = tmp_layout.hermes_dir
    audit.mkdir(parents=True, exist_ok=True)
    (audit / "a2a_audit.jsonl").write_text(
        "\n".join(
            json.dumps(
                {"ts": 1.0, "direction": "inbound", "peer": "manager-node", "task_id": tid, "summary": "s"}
            )
            for tid in ("sim-specialist-node",)
        )
        + "\n",
        encoding="utf-8",
    )
    ctx = _ctx(tmp_layout, peers_config, fake_http=fake_http)
    assert run_test(ctx) == 0
    out = capsys.readouterr().out
    assert "L1" in out and "L3" in out and "L5" in out and "PASS" in out


def test_harness_level1_alone_is_not_pass(tmp_layout, peers_config, capsys):
    """L1 success with L3 failing must be a FAIL (no ping-only passes)."""
    url = "http://127.0.0.1:9900"
    fake_http = {
        f"{url}/.well-known/agent-card.json": (200, {"name": "specialist-node"}),
        f"{url}/": (500, {}),  # message/send fails
    }
    ctx = _ctx(tmp_layout, peers_config, fake_http=fake_http)
    assert run_test(ctx, levels=3) == 1
    out = capsys.readouterr().out
    assert "NOT a pass" in out


def test_harness_reports_requires_test_for_l4_without_reverse(tmp_layout, peers_config, capsys):
    url = "http://127.0.0.1:9900"
    fake_http = {
        f"{url}/.well-known/agent-card.json": (200, {"name": "specialist-node"}),
        f"{url}/": (200, {"__echo__": True}),
    }
    ctx = _ctx(tmp_layout, peers_config, fake_http=fake_http)
    assert run_test(ctx, levels=4) == 0
    out = capsys.readouterr().out
    assert "REQUIRES_TEST" in out or "L4" in out