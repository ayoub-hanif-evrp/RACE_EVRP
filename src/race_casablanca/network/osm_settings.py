"""Shared OSMnx / Overpass configuration with mirror failover."""

from __future__ import annotations

import osmnx as ox

OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api",
    "https://overpass.kumi.systems/api",
    "https://overpass.openstreetmap.fr/api",
]


def configure_osmnx(*, use_cache: bool = True, overpass_endpoint: str | None = None) -> None:
    ox.settings.use_cache = use_cache
    ox.settings.timeout = 300
    ox.settings.requests_timeout = 180
    if overpass_endpoint:
        ox.settings.overpass_url = overpass_endpoint
    else:
        ox.settings.overpass_url = OVERPASS_ENDPOINTS[0]


def try_overpass_endpoints():
    """Yield Overpass base URLs to try in order."""

    yield from OVERPASS_ENDPOINTS
