"""Integration adapter boundaries: status/doctor/backup with fake plumbing."""

from __future__ import annotations

import json

from safeharbor.context import Context, HttpClient, ServiceControl
from safeharbor.integrations import REGISTRY


def _ctx_with_services(tmp_layout, *, active=None, http_responses=None):
    active = active or {}
    http = HttpClient(simulate=True, fake_responses=http_responses or {})
    ctx = Context(
        layout=tmp_layout,
        simulate=True,
        service=ServiceControl(simulate=True, fake_active=active),
        http=http,
    )
    return ctx


def test_restate_status_ok(tmp_layout):
    ctx = _ctx_with_services(
        tmp_layout,
        active={"restate.service": True},
        http_responses={"http://127.0.0.1:9070/health": (200, {})},
    )
    result = REGISTRY["restate"].status(ctx)
    assert result.state == "OK"
    assert "200" in result.detail


def test_restate_status_fails_on_bad_health(tmp_layout):
    ctx = _ctx_with_services(
        tmp_layout,
        active={"restate.service": True},
        http_responses={"http://127.0.0.1:9070/health": (503, {})},
    )
    result = REGISTRY["restate"].status(ctx)
    assert result.state == "FAIL"


def test_restate_not_configured_when_unit_absent(tmp_layout):
    ctx = _ctx_with_services(tmp_layout, active={})
    result = REGISTRY["restate"].status(ctx)
    assert result.state == "NOT_CONFIGURED"


def test_jnaapakam_status_ok(tmp_layout):
    ctx = _ctx_with_services(
        tmp_layout,
        active={"jnaapakam.service": True},
        http_responses={
            "http://127.0.0.1:8889/status": (200, {"total_memories": 3})
        },
    )
    result = REGISTRY["jnaapakam"].status(ctx)
    assert result.state == "OK"
    assert "3" in result.detail


def test_hermes_status_ok(tmp_layout):
    ctx = _ctx_with_services(tmp_layout, active={"hermes-manager.service": True})
    result = REGISTRY["hermes"].status(ctx)
    assert result.state == "OK"


def test_doctor_results_are_state_shaped(tmp_layout):
    ctx = _ctx_with_services(tmp_layout)
    for name, integration in REGISTRY.items():
        for check in integration.doctor(ctx):
            assert check.state in ("OK", "WARN", "FAIL", "NOT_CONFIGURED", "REQUIRES_TEST")
            assert check.name.startswith(name)


def test_backup_records_strategy(tmp_layout, tmp_path):
    ctx = _ctx_with_services(tmp_layout)
    stage = tmp_path / "stage"
    stage.mkdir()
    # with nothing resident, components report 'skipped' rather than failing
    for name, integration in REGISTRY.items():
        component = integration.backup(stage, ctx)
        assert component.strategy in ("skipped", "api_export", "quiesced_copy")