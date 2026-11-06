"""Free-flow speed parsing and fallbacks."""

from __future__ import annotations

import re
from pathlib import Path

import yaml


def load_speed_config(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def parse_maxspeed(value) -> float | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    if not text or text in {"nan", "none"}:
        return None
    if "mph" in text:
        match = re.search(r"(\d+(?:\.\d)?)", text)
        return float(match.group(1)) * 1.60934 if match else None
    match = re.search(r"(\d+(?:\.\d)?)", text)
    return float(match.group(1)) if match else None


def free_flow_speed_kmh(highway, maxspeed, config: dict) -> float:
    parsed = parse_maxspeed(maxspeed)
    if parsed and parsed > 0:
        return float(parsed)
    table = config.get("free_flow_speed_kmh", {})
    if isinstance(highway, list):
        highway = highway[0] if highway else "default"
    key = str(highway) if highway is not None else "default"
    return float(table.get(key, table.get("default", 30)))
