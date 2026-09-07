"""Integration layer.

Safe Harbor core owns deployment, recovery, validation and orchestration.
Each upstream project is reached exclusively through a small adapter that
implements :class:`Integration`. New upstream components (or replacements
for the Gen1 trio) are added by implementing the interface — core code is
not rewritten.
"""

from __future__ import annotations

from .base import Integration
from .hermes import HermesIntegration
from .jnaapakam import JnaapakamIntegration
from .restate import RestateIntegration

#: Order matters: dependencies first (Restate has no deps; jñāpakaṁ and
#: Hermes are independent of each other, but Hermes is last as the agent
#: runtime that talks to the rest).
REGISTRY: dict[str, Integration] = {
    "restate": RestateIntegration(),
    "jnaapakam": JnaapakamIntegration(),
    "hermes": HermesIntegration(),
}

__all__ = ["Integration", "REGISTRY", "HermesIntegration", "JnaapakamIntegration", "RestateIntegration"]