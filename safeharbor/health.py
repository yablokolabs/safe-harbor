"""Health-check state model.

``safeharbor status`` is a fast operational summary; ``safeharbor doctor``
is the deeper validation. Both report per-check states. A state is evidence
based — a running process is NOT treated as semantic health on its own.

States:

    OK              — verified healthy by an actual probe
    WARN            — usable but degraded / unverified detail
    FAIL            — verified broken
    NOT_CONFIGURED  — component intentionally absent or never configured
    REQUIRES_TEST   — cannot be verified on this machine (missing target OS,
                      missing peer hardware, needs the integration lab)
"""

from __future__ import annotations

from dataclasses import dataclass, field

OK = "OK"
WARN = "WARN"
FAIL = "FAIL"
NOT_CONFIGURED = "NOT_CONFIGURED"
REQUIRES_TEST = "REQUIRES_TEST"

STATES = (OK, WARN, FAIL, NOT_CONFIGURED, REQUIRES_TEST)

#: Order used for sorting output (FAIL first, then WARN, ...).
_SORT_ORDER = {FAIL: 0, WARN: 1, REQUIRES_TEST: 2, NOT_CONFIGURED: 3, OK: 4}


@dataclass
class CheckResult:
    """One named check with a state and human-readable detail."""

    name: str
    state: str = REQUIRES_TEST
    detail: str = ""
    #: Optional machine-readable evidence (e.g. the version string found).
    evidence: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.state not in STATES:
            raise ValueError(f"unknown state {self.state!r}")

    @property
    def is_ok(self) -> bool:
        return self.state == OK

    def render(self) -> str:
        detail = f" — {self.detail}" if self.detail else ""
        return f"{self.state:<14} {self.name}{detail}"


def worst(results: list[CheckResult]) -> str:
    """Worst state across a list, FAIL > WARN > REQUIRES_TEST > NOT_CONFIGURED > OK."""
    if not results:
        return OK
    return min((r.state for r in results), key=lambda s: _SORT_ORDER[s])


def passed(results: list[CheckResult]) -> bool:
    """True when nothing is FAIL. WARN/REQUIRES_TEST/NOT_CONFIGURED are not failures."""
    return all(r.state != FAIL for r in results)


def sorted_results(results: list[CheckResult]) -> list[CheckResult]:
    return sorted(results, key=lambda r: (_SORT_ORDER[r.state], r.name))