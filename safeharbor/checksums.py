"""Checksum helpers.

Safe Harbor uses standard SHA-256 everywhere: artifact verification,
backup content hashing, and generation seals. Nothing proprietary.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

#: Block size for streaming hashing of large artifacts.
_CHUNK = 1024 * 1024


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path | str) -> str:
    """Return the lowercase hex SHA-256 of a file, streaming in chunks."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_sha256(path: Path | str, expected: str) -> bool:
    """Return True when the file's SHA-256 equals ``expected`` (case-insensitive)."""
    return sha256_file(path).lower() == expected.strip().lower()


def sha256_of_tree(root: Path) -> dict[str, str]:
    """Hash every regular file under ``root``, relative path -> hex digest.

    Used to seal a backup staging tree before it is archived. Directory
    structure itself is captured by the backup manifest, not by this map.
    """
    hashes: dict[str, str] = {}
    if not root.is_dir():
        return hashes
    for path in sorted(root.rglob("*")):
        if path.is_file():
            hashes[str(path.relative_to(root))] = sha256_file(path)
    return hashes