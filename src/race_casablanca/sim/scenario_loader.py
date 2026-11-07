"""Load Stage-1 scenarios into online simulator inputs without reading witnesses."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import networkx as nx
import osmnx as ox
import pandas as pd
import yaml

from race_casablanca.network.travel_time import CongestionModel
from race_casablanca.paths import config_dir, roads_dir, traffic_dir
from race_casablanca.sim.types import Request, RequestStatus


@dataclass
class LoadedScenario:
    scenario_id: str
    requests: list[Request]
    fleet: dict
    depot_node: int
    shift_start_s: float
    shift_end_s: float
    day: str
    metadata: dict
    graph: nx.MultiDiGraph | None = None
    model: CongestionModel | None = None


def load_congestion_model() -> CongestionModel:
    city = pd.read_csv(traffic_dir() / "tti_citywide_hour.csv")
    citywide = pd.Series(city["tti_factor"].to_numpy(), index=city["hour"].astype(int))
    zone_path = traffic_dir() / "tti_zone_day_hour.csv"
    zone = pd.read_csv(zone_path) if zone_path.exists() else None
    return CongestionModel(citywide_hour=citywide, zone_day_hour=zone)


def load_drive_graph() -> nx.MultiDiGraph:
    return ox.load_graphml(roads_dir() / "casablanca_drive.graphml")


def load_fleet_defaults() -> dict:
    path = config_dir() / "fleet_default.yaml"
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_scenario(
    scenario_dir: Path | str,
    *,
    load_network: bool = True,
    day: str = "Monday",
    graph: nx.MultiDiGraph | None = None,
    model: CongestionModel | None = None,
) -> LoadedScenario:
    scenario_dir = Path(scenario_dir)
    meta = json.loads((scenario_dir / "scenario_metadata.json").read_text(encoding="utf-8"))
    # Policies must never read offline feasibility witnesses.
    if (scenario_dir / "witnesses").exists():
        # Presence is fine; we simply never open that directory.
        pass

    req_df = pd.read_csv(scenario_dir / "requests.csv")
    requests: list[Request] = []
    for _, row in req_df.iterrows():
        requests.append(
            Request(
                request_id=str(row["request_id"]),
                snap_node=int(row["snap_node"]),
                release_s=float(row["release_min"]) * 60.0,
                tw_start_s=float(row["tw_start_min"]) * 60.0,
                tw_end_s=float(row["tw_end_min"]) * 60.0,
                service_s=float(row["service_min"]) * 60.0,
                weight_kg=float(row["weight_kg"]),
                status=RequestStatus.UNRELEASED,
            )
        )

    fleet = dict(meta.get("fleet") or load_fleet_defaults())
    depot_node = int(meta["depot"]["snap_node"])
    sp = meta.get("shift_policy") or {}
    start_h = float(sp.get("start_hour", 8))
    horizon_h = float(sp.get("horizon_hours", 8))
    shift_start_s = start_h * 3600.0
    shift_end_s = (start_h + horizon_h) * 3600.0

    g = graph
    m = model
    if load_network:
        if g is None:
            g = load_drive_graph()
        if m is None:
            m = load_congestion_model()

    sid = f"{meta.get('split', 'unknown')}/{scenario_dir.name}"
    return LoadedScenario(
        scenario_id=sid,
        requests=requests,
        fleet=fleet,
        depot_node=depot_node,
        shift_start_s=shift_start_s,
        shift_end_s=shift_end_s,
        day=day,
        metadata=meta,
        graph=g,
        model=m,
    )
