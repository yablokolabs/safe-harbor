"""Runtime context shared by every integration adapter.

The context carries the resolved filesystem layout plus small, replaceable
helpers for the side effects adapters need: service lifecycle control
(systemd), outbound HTTP probes, and command execution. Tests replace these
helpers (or use ``simulate=True``) so no adapter can touch a real machine
during the local test suite.
"""

from __future__ import annotations

import json
import shlex
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

#: Socket-probe signature used by the A2A harness.
ProbeFn = Callable[[Any], tuple[int, str]]

from .paths import Layout


class ServiceError(Exception):
    pass


@dataclass
class ServiceControl:
    """systemd unit lifecycle. In simulate mode every call is a no-op."""

    simulate: bool = False
    #: Override for tests: map unit name -> bool active
    fake_active: dict[str, bool] = field(default_factory=dict)

    def is_active(self, unit: str) -> bool | None:
        """Return None when the unit is unknown (e.g. not installed)."""
        if self.simulate:
            return self.fake_active.get(unit)  # None = not installed
        if not self._unit_exists(unit):
            return None
        proc = subprocess.run(
            ["systemctl", "is-active", unit],
            capture_output=True, text=True, timeout=10,
        )
        return proc.returncode == 0

    def _unit_exists(self, unit: str) -> bool:
        proc = subprocess.run(
            ["systemctl", "cat", unit],
            capture_output=True, text=True, timeout=10,
        )
        return proc.returncode == 0

    def stop(self, unit: str) -> None:
        if self.simulate:
            return
        proc = subprocess.run(
            ["systemctl", "stop", unit], capture_output=True, text=True, timeout=60
        )
        if proc.returncode != 0:
            raise ServiceError(f"systemctl stop {unit}: {proc.stderr.strip()}")

    def start(self, unit: str) -> None:
        if self.simulate:
            return
        proc = subprocess.run(
            ["systemctl", "start", unit], capture_output=True, text=True, timeout=60
        )
        if proc.returncode != 0:
            raise ServiceError(f"systemctl start {unit}: {proc.stderr.strip()}")

    def restart(self, unit: str) -> None:
        if self.simulate:
            return
        proc = subprocess.run(
            ["systemctl", "restart", unit], capture_output=True, text=True, timeout=60
        )
        if proc.returncode != 0:
            raise ServiceError(f"systemctl restart {unit}: {proc.stderr.strip()}")


@dataclass
class HttpClient:
    """Minimal HTTP client (stdlib only)."""

    simulate: bool = False
    #: For tests: url -> (status, body) canned responses
    fake_responses: dict[str, tuple[int, Any]] = field(default_factory=dict)

    def _request(
        self,
        url: str,
        *,
        method: str = "GET",
        payload: dict[str, Any] | None = None,
        token: str | None = None,
        timeout: float = 5.0,
    ) -> tuple[int, Any]:
        """Perform a request. Returns (status, body); body is parsed JSON when possible.
        A transport failure returns status -1 with an error dict."""
        if self.simulate:
            # Simulate mode NEVER touches the network — not even localhost.
            if url in self.fake_responses:
                return self.fake_responses[url]
            return -1, {"error": "simulated network disabled"}
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = urllib.request.Request(url, data=data, method=method)
        if payload is not None:
            request.add_header("Content-Type", "application/json")
        if token:
            request.add_header("Authorization", f"Bearer {token}")
        try:
            with urllib.request.urlopen(request, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                try:
                    return resp.status, json.loads(raw)
                except json.JSONDecodeError:
                    return resp.status, raw
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            try:
                return exc.code, json.loads(raw)
            except json.JSONDecodeError:
                return exc.code, raw
        except OSError as exc:
            return -1, {"error": str(exc)}

    def get(self, url: str, *, token: str | None = None, timeout: float = 5.0) -> tuple[int, Any]:
        return self._request(url, token=token, timeout=timeout)

    def post(
        self,
        url: str,
        payload: dict[str, Any],
        *,
        token: str | None = None,
        timeout: float = 30.0,
    ) -> tuple[int, Any]:
        return self._request(url, method="POST", payload=payload, token=token, timeout=timeout)


@dataclass
class Context:
    """Everything an adapter needs, without touching globals."""

    layout: Layout
    simulate: bool = False
    dry_run: bool = False
    service: ServiceControl = field(default_factory=ServiceControl)
    http: HttpClient = field(default_factory=HttpClient)
    #: Overridable network probe for the A2A harness (tests replace it).
    socket_probe: ProbeFn | None = None

    def __post_init__(self) -> None:
        self.service.simulate = self.simulate
        self.http.simulate = self.simulate
        if self.simulate and self.socket_probe is None:
            self.socket_probe = lambda peer: (0, "simulated")

    def run_cmd(self, cmd: list[str], *, timeout: int = 60) -> tuple[int, str]:
        """Run a command; returns (exit_code, combined output). Never raises."""
        if self.simulate:
            return 0, ""
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            return proc.returncode, (proc.stdout + proc.stderr).strip()
        except FileNotFoundError:
            return 127, f"command not found: {shlex.join(cmd)}"
        except subprocess.TimeoutExpired:
            return 124, f"timed out after {timeout}s: {shlex.join(cmd)}"