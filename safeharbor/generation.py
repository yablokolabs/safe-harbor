"""Generation / environment metadata.

The generation manifest records what the environment WAS built from
(component pins, OS, architecture) without binding persistent resident
identity to hostname, MAC, disk UUID, CPU, serial or model — those are
environment metadata at most, never resident identity.
"""

from __future__ import annotations

import json

from .context import Context
from .integrations import REGISTRY
from .manifest import (
    build_generation_manifest,
    load_current_generation,
    validate_generation_manifest,
    write_generation_manifest,
)


def record(ctx: Context) -> int:
    """Build and persist a generation manifest from installed versions."""
    components: dict[str, dict] = {}
    for name, integration in REGISTRY.items():
        version = integration.version(ctx)
        if version:
            components[name] = {"version": version}
    if not components:
        print("No component versions detected — is Safe Harbor deployed?")
        return 1
    manifest = build_generation_manifest(components=components)
    path = write_generation_manifest(ctx.layout, manifest)
    print(f"Recorded generation manifest: {path}")
    return 0


def show(ctx: Context, *, machine_readable: bool = False) -> int:
    generation = load_current_generation(ctx.layout)
    if generation is None:
        print("No generation manifest recorded.")
        return 1
    if machine_readable:
        print(json.dumps(generation, indent=2, sort_keys=True))
    else:
        print(json.dumps(generation, indent=2, sort_keys=True))
    return 0


def validate(ctx: Context) -> int:
    generation = load_current_generation(ctx.layout)
    if generation is None:
        print("No generation manifest recorded.")
        return 1
    try:
        validate_generation_manifest(generation)
    except Exception as exc:
        print(f"INVALID: {exc}")
        return 1
    print("Generation manifest valid.")
    return 0