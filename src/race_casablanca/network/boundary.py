"""Study-area boundary from workbook communes matched to OSM admin polygons."""

from __future__ import annotations

import re
import time
import unicodedata
from pathlib import Path

import geopandas as gpd
import osmnx as ox
import pandas as pd
from shapely.geometry import box
from shapely.ops import unary_union


def _norm(name: str) -> str:
    text = unicodedata.normalize("NFKD", str(name))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower()
    text = text.replace("'", "'").replace("`", "'").replace("-", " ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


# Workbook name -> candidate OSM admin names (normalized later).
ALIASES = {
    "echchallalate": ["ech challalate", "challalate", "echchallalate", "ech challalate"],
    "sidi maarouf": ["sidi maarouf"],
    "anfa": ["anfa", "arrondissement d anfa"],
    "assoukhour assawda": [
        "assoukhour assawda",
        "asoukhour assawda",
        "roches noires",
        "assoukhour",
    ],
    "ben msick": ["ben m sick", "ben msik", "ben msick", "ibn msick"],
    "bou chentouf": ["bou chentouf", "bouchentouf"],
    "el maarif": ["maarif", "el maarif", "ma arif"],
    "hay hassani": ["hay hassani"],
    "hay mohammadi": ["hay mohammadi"],
    "ain chock": ["ain chock", "ain choc"],
    "ain sebaa": ["ain sebaa"],
    "al fida": ["al fida", "fida", "al fida"],
    "al idrissia": ["al idrissia", "idrissia"],
    "lissasfa": ["lissasfa", "lysasfa"],
    "mers sultan": ["mers sultan"],
    "moulay rachid": ["moulay rachid"],
    "sidi belyout": ["sidi belyout"],
    "sidi moumen": ["sidi moumen"],
    "sidi othmane": ["sidi othmane", "sidi othman"],
    "ahl laghlam": ["ahl laghlam", "ahl loghlam"],
    "sidi bernoussi": ["sidi bernoussi"],
    "moulay youssef": ["moulay youssef"],
}


def fetch_admin_in_envelope(west: float, south: float, east: float, north: float) -> gpd.GeoDataFrame:
    """Fetch polygonal administrative features intersecting the workbook envelope."""

    from race_casablanca.network.osm_settings import OVERPASS_ENDPOINTS, configure_osmnx

    polygon = box(west, south, east, north)
    last_error: Exception | None = None
    for endpoint in OVERPASS_ENDPOINTS:
        try:
            configure_osmnx(use_cache=True, overpass_endpoint=endpoint)
            features = ox.features_from_polygon(polygon, tags={"boundary": "administrative"})
            if features.empty:
                continue
            polys = features[features.geometry.type.isin(["Polygon", "MultiPolygon"])].copy()
            if "name" not in polys.columns:
                continue
            polys = polys[polys["name"].notna()].copy().reset_index()
            return polys
        except Exception as exc:  # noqa: BLE001
            last_error = exc
    raise RuntimeError(f"Could not fetch OSM admin polygons. Last error: {last_error}")


def _score_candidate(name_norm: str, aliases: list[str], admin_level, envelope) -> float:
    score = 0.0
    for alias in aliases:
        if len(alias) < 4:
            continue  # avoid short-token false positives
        if name_norm == alias:
            score += 10.0
        elif alias in name_norm or name_norm in alias:
            score += 5.0
    if score <= 0:
        return 0.0
    if admin_level is not None and str(admin_level) in {"8", "9", "10"}:
        score += 2.0
    if admin_level is not None and str(admin_level) in {"4", "5", "6"}:
        score -= 5.0  # region/prefecture too coarse
    return score


def match_admin_polygons(
    communes: pd.DataFrame,
    admin: gpd.GeoDataFrame,
    envelope=None,
) -> gpd.GeoDataFrame:
    admin = admin.copy()
    admin["name_norm"] = admin["name"].map(_norm)
    rows = []
    for _, commune in communes.iterrows():
        key = _norm(commune["commune"])
        aliases = [_norm(a) for a in ALIASES.get(key, [key])]
        aliases.append(key)
        scored = []
        for idx, row in admin.iterrows():
            score = _score_candidate(row["name_norm"], aliases, row.get("admin_level"), envelope)
            if score <= 0:
                continue
            geom = row.geometry
            if geom is None or geom.is_empty:
                continue
            if envelope is not None and not geom.intersects(envelope):
                continue
            # Reject huge prefecture/city containers that dwarf the envelope.
            if envelope is not None and geom.area > envelope.area * 1.5:
                score -= 8.0
            if score >= 5.0:
                scored.append((score, idx, row))
        if not scored:
            rows.append(
                {
                    "workbook_commune": commune["commune"],
                    "zip_code": commune["zip_code"],
                    "matched": False,
                    "osm_name": None,
                    "osm_id": None,
                    "admin_level": None,
                    "match_score": None,
                }
            )
            continue
        scored.sort(key=lambda t: t[0], reverse=True)
        _, _, chosen = scored[0]
        rows.append(
            {
                "workbook_commune": commune["commune"],
                "zip_code": commune["zip_code"],
                "matched": True,
                "osm_name": chosen["name"],
                "osm_id": chosen.get("osmid", chosen.get("osm_id")),
                "admin_level": chosen.get("admin_level"),
                "match_score": float(scored[0][0]),
                "geometry": chosen.geometry,
            }
        )
    return gpd.GeoDataFrame(rows, geometry="geometry", crs=admin.crs)


def match_communes_via_nominatim(
    communes: pd.DataFrame,
    envelope=None,
    pause_s: float = 1.1,
) -> gpd.GeoDataFrame:
    """Fallback Nominatim matching with envelope validation."""

    rows = []
    for _, commune in communes.iterrows():
        key = _norm(commune["commune"])
        aliases = ALIASES.get(key, [commune["commune"]])
        hit = None
        used_query = None
        best_score = -1.0
        for alias in aliases:
            queries = [
                f"Arrondissement de {alias}, Casablanca, Morocco",
                f"Arrondissement d'{alias}, Casablanca, Morocco",
                f"Commune de {alias}, Morocco",
                f"{alias}, Casablanca, Morocco",
            ]
            for query in queries:
                try:
                    gdf = ox.geocode_to_gdf(query)
                except Exception:  # noqa: BLE001
                    gdf = None
                time.sleep(pause_s)
                if gdf is None or gdf.empty:
                    continue
                geom = gdf.geometry.iloc[0]
                if geom is None or geom.is_empty or geom.geom_type == "Point":
                    continue
                display = str(gdf.iloc[0].get("display_name", "")).lower()
                score = 0.0
                if "casablanca" in display or "mohammedia" in display or "nouaceur" in display:
                    score += 3.0
                if "arrondissement" in display or "commune" in display:
                    score += 2.0
                if envelope is not None and geom.intersects(envelope):
                    score += 2.0
                if envelope is not None and geom.area > envelope.area * 1.5:
                    score -= 10.0
                if score > best_score:
                    best_score = score
                    hit = gdf
                    used_query = query
        if hit is None or best_score < 2.0:
            rows.append(
                {
                    "workbook_commune": commune["commune"],
                    "zip_code": commune["zip_code"],
                    "matched": False,
                    "osm_name": None,
                    "osm_id": None,
                    "nominatim_query": None,
                    "geometry": None,
                }
            )
            continue
        chosen = hit.iloc[0]
        rows.append(
            {
                "workbook_commune": commune["commune"],
                "zip_code": commune["zip_code"],
                "matched": True,
                "osm_name": chosen.get("display_name") or chosen.get("name"),
                "osm_id": chosen.get("osm_id"),
                "nominatim_query": used_query,
                "geometry": chosen.geometry,
            }
        )
    return gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326")


def fill_unmatched_with_od_hulls(
    matched: gpd.GeoDataFrame,
    coordinates: pd.DataFrame,
    buffer_m: float = 400.0,
) -> gpd.GeoDataFrame:
    """Documented geometric fallback for communes without a trusted OSM admin match.

    Uses the convex hull of workbook OD coordinate points for that commune,
    buffered in a local projected CRS. This is not an OSM administrative claim.
    """

    out = matched.copy()
    if out.crs is None:
        out = out.set_crs("EPSG:4326")
    for idx, row in out[~out["matched"]].iterrows():
        pts = coordinates[coordinates["commune"] == row["workbook_commune"]]
        if pts.empty:
            continue
        gdf = gpd.GeoDataFrame(
            geometry=gpd.points_from_xy(pts["lon"], pts["lat"]),
            crs="EPSG:4326",
        )
        projected = gdf.to_crs(gdf.estimate_utm_crs())
        hull = projected.unary_union.convex_hull.buffer(buffer_m)
        hull_wgs = gpd.GeoSeries([hull], crs=projected.crs).to_crs("EPSG:4326").iloc[0]
        out.at[idx, "matched"] = True
        out.at[idx, "osm_name"] = None
        out.at[idx, "osm_id"] = None
        out.at[idx, "admin_level"] = None
        out.at[idx, "match_score"] = 0.0
        out.at[idx, "geometry"] = hull_wgs
        out.at[idx, "match_method"] = "workbook_od_convex_hull_buffer"
    if "match_method" not in out.columns:
        out["match_method"] = None
    out.loc[out["matched"] & out["match_method"].isna(), "match_method"] = "osm_admin_name_match"
    return out


def union_boundary(matched: gpd.GeoDataFrame):
    geoms = [geom for geom in matched.loc[matched["matched"], "geometry"] if geom is not None]
    if not geoms:
        raise RuntimeError("No commune polygons matched; cannot build study boundary.")
    return unary_union(geoms)


def write_boundary_products(matched: gpd.GeoDataFrame, zones_dir: Path) -> dict:
    zones_dir.mkdir(parents=True, exist_ok=True)
    matched_path = zones_dir / "zone_crosswalk.gpkg"
    matched.to_file(matched_path, layer="zones", driver="GPKG")
    boundary = union_boundary(matched)
    boundary_gdf = gpd.GeoDataFrame({"name": ["casablanca_study_area"]}, geometry=[boundary], crs=matched.crs)
    boundary_path = zones_dir / "study_boundary.gpkg"
    boundary_gdf.to_file(boundary_path, layer="boundary", driver="GPKG")
    crosswalk_csv = zones_dir / "zone_crosswalk.csv"
    matched.drop(columns="geometry").to_csv(crosswalk_csv, index=False)
    return {
        "n_workbook_communes": int(len(matched)),
        "n_matched": int(matched["matched"].sum()),
        "n_unmatched": int((~matched["matched"]).sum()),
        "unmatched": matched.loc[~matched["matched"], "workbook_commune"].tolist(),
        "boundary_path": str(boundary_path),
        "crosswalk_path": str(crosswalk_csv),
        "definition": (
            "Union of OSM administrative polygons matched to the 22 workbook commune names. "
            "Not an arbitrary rectangle and not the full Casablanca-Settat region."
        ),
    }
