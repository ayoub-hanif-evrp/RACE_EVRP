"""Shared I/O helpers."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def download_file(url: str, destination: Path, timeout: int = 120, resume: bool = True) -> None:
    """Download a URL to destination, optionally resuming a partial file."""

    destination.parent.mkdir(parents=True, exist_ok=True)
    headers: dict[str, str] = {}
    mode = "wb"
    existing = destination.stat().st_size if destination.exists() else 0
    if resume and existing > 0:
        headers["Range"] = f"bytes={existing}-"
        mode = "ab"
    with requests.get(url, stream=True, timeout=timeout, headers=headers) as response:
        # If server rejects Range, restart from scratch.
        if response.status_code == 416:
            destination.unlink(missing_ok=True)
            return download_file(url, destination, timeout=timeout, resume=False)
        if existing > 0 and response.status_code == 200 and "Range" in headers:
            # Server ignored Range; rewrite.
            mode = "wb"
            existing = 0
        response.raise_for_status()
        with destination.open(mode) as handle:
            for chunk in response.iter_content(chunk_size=1 << 20):
                if chunk:
                    handle.write(chunk)
