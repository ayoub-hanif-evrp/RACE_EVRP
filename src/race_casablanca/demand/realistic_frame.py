"""Realistic pickup sampling frame from OSM features (not random map dots).

Each candidate is an OpenStreetMap building / shop / office / amenity feature.
``lat``/``lon`` are the feature geometry (point or building-polygon centroid).
``snap_node`` is only the nearest drive-graph access node for routing — it is
not the customer location.
"""

from __future__ import annotations

import re

import pandas as pd

# Untyped / non-service locations — excluded for realism.
EXCLUDE_CATEGORIES = frozenset(
    {
        "building=yes",  # generic footprint without building type
        "unknown",
        "amenity=parking",
        "amenity=parking_entrance",
        "amenity=fuel",
        "amenity=bench",
        "amenity=waste_basket",
        "amenity=toilets",
        "amenity=atm",
        "amenity=vending_machine",
        "amenity=drinking_water",
        "amenity=place_of_worship",
    }
)

# Explicit building types that are real structures.
TYPED_BUILDINGS = frozenset(
    {
        "building=commercial",
        "building=office",
        "building=retail",
        "building=industrial",
        "building=warehouse",
        "building=apartments",
        "building=house",
        "building=residential",
        "building=detached",
        "building=terrace",
        "building=semidetached_house",
    }
)

# Logistics-relevant amenities / destinations.
ALLOW_AMENITY = frozenset(
    {
        "amenity=restaurant",
        "amenity=cafe",
        "amenity=fast_food",
        "amenity=bank",
        "amenity=pharmacy",
        "amenity=clinic",
        "amenity=hospital",
        "amenity=doctors",
        "amenity=dentist",
        "amenity=school",
        "amenity=university",
        "amenity=college",
        "amenity=kindergarten",
        "amenity=marketplace",
        "amenity=post_office",
        "amenity=library",
        "amenity=townhall",
        "amenity=community_centre",
        "amenity=police",
        "amenity=fire_station",
    }
)


def _has_name(series: pd.Series) -> pd.Series:
    s = series.fillna("").astype(str).str.strip()
    return (s != "") & (~s.str.lower().isin({"nan", "none", "null"}))


def is_realistic_category(category: str) -> bool:
    cat = str(category or "")
    if cat in EXCLUDE_CATEGORIES:
        return False
    if cat in TYPED_BUILDINGS or cat in ALLOW_AMENITY:
        return True
    if cat.startswith("shop=") or cat.startswith("office="):
        return True
    return False


def filter_realistic_pickup_candidates(
    df: pd.DataFrame,
    *,
    require_accessible: bool = True,
    max_snap_distance_m: float = 150.0,
    prefer_named_amenities: bool = True,
) -> pd.DataFrame:
    """Return OSM features suitable as parcel/customer pickup addresses."""
    out = df.copy()
    if require_accessible and "accessible" in out.columns:
        out = out[out["accessible"] == True]  # noqa: E712
    if "snap_distance_m" in out.columns:
        out = out[out["snap_distance_m"].fillna(1e9) <= float(max_snap_distance_m)]
    if "osmid" in out.columns:
        out = out[out["osmid"].notna()]
    out = out[out["category"].map(is_realistic_category)].copy()

    # Drop residual non-service amenities that slipped through prefix rules.
    out = out[~out["category"].isin(EXCLUDE_CATEGORIES)].copy()

    if prefer_named_amenities and "name" in out.columns:
        named = _has_name(out["name"])
        is_shop_office = out["category"].str.startswith(("shop=", "office="))
        is_amenity = out["category"].str.startswith("amenity=")
        is_building = out["category"].str.startswith("building=")
        # Shops/offices/amenities: prefer named (more identifiable real places).
        # Typed buildings: keep even if unnamed (still real OSM building footprints).
        keep = is_building | ((is_shop_office | is_amenity) & named) | (is_shop_office & ~named)
        # If a shop/office has no name, still keep (OSM feature exists); amenities without name drop.
        keep = is_building | is_shop_office | (is_amenity & named)
        out = out[keep].copy()

    out["location_semantics"] = "osm_feature_centroid_or_point"
    out["routing_access_node"] = out["snap_node"]
    out["is_random_map_projection"] = False
    out["is_observed_order"] = False
    return out.reset_index(drop=True)


def realism_summary(raw: pd.DataFrame, filtered: pd.DataFrame) -> dict:
    return {
        "n_raw_accessible": int((raw["accessible"] == True).sum()) if "accessible" in raw.columns else len(raw),  # noqa: E712
        "n_realistic": int(len(filtered)),
        "excluded_building_yes": True,
        "note": (
            "Customers are sampled from real OSM buildings/POIs. "
            "Coordinates are feature centroids/points, not random road projections. "
            "snap_node is routing access only."
        ),
    }
