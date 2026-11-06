"""File integrity helpers."""

from __future__ import annotations

import hashlib
from pathlib import Path


def sha256_file(path: Path, chunk_bytes: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            block = handle.read(chunk_bytes)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def same_bytes(path: Path, expected_sha256: str, expected_size: int | None = None) -> bool:
    if expected_size is not None and path.stat().st_size != expected_size:
        return False
    return sha256_file(path) == expected_sha256.lower()
