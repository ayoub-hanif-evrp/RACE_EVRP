"""On-the-fly Casablanca training episodes from the frozen demand generator.

Scientific contract
-------------------
- Geography, zone weights, candidates, traffic, depot, and regime configs are
  frozen release assets (not regenerated randomly).
- Customer requests / time windows are synthetic and regenerated per episode.
- Seeds are drawn only from TRAIN_SEED_RANGE and never overlap locked_final,
  evaluation_v1/default, or release split seeds.
- locked_final must not be loaded or tuned against by this module.

This makes the training set *large enough for MARL* without claiming observed
courier orders.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from race_casablanca.demand.generator import (
    generate_requests,
    load_demand_config,
    load_demand_zone_weights,
    zone_sampling_weights_from_table,
)
from race_casablanca.marl.seed_banks import (
    REGIME_ORDER,
    TRAIN_SEED_RANGE,
    assert_train_seed_allowed,
    curriculum_regime,
    episode_train_seed,
)
from race_casablanca.paths import (
    candidates_dir,
    config_dir,
    fleet_dir,
    project_root,
)
from race_casablanca.sim.scenario_loader import (
    load_congestion_model,
    load_drive_graph,
    load_fleet_defaults,
)
from race_casablanca.sim.types import Request, RequestStatus


def _requests_from_frame(df: pd.DataFrame) -> list[Request]:
    out: list[Request] = []
    for _, row in df.iterrows():
        snap = row.get("snap_node")
        if pd.isna(snap):
            raise ValueError(f"Request {row.get('request_id')} missing snap_node")
        out.append(
            Request(
                request_id=str(row["request_id"]),
                snap_node=int(snap),
                release_s=float(row["release_min"]) * 60.0,
                tw_start_s=float(row["tw_start_min"]) * 60.0,
                tw_end_s=float(row["tw_end_min"]) * 60.0,
                service_s=float(row["service_min"]) * 60.0,
                weight_kg=float(row["weight_kg"]),
                status=RequestStatus.UNRELEASED,
            )
        )
    return out


@dataclass
class ProceduralEpisodeGenerator:
    """Cached frozen inputs + per-episode synthetic request sampling."""

    config: dict
    candidates: pd.DataFrame
    zone_weights: pd.Series
    fleet: dict
    depot: dict
    graph: Any = None
    model: Any = None
    load_network: bool = True
    _episode_counter: int = field(default=0, init=False)

    @classmethod
    def from_release(cls, *, load_network: bool = True) -> "ProceduralEpisodeGenerator":
        config = load_demand_config(config_dir() / "demand_default.yaml")
        weights_path = project_root() / "data" / "casablanca" / "zones" / "demand_zone_weights.csv"
        candidates_path = candidates_dir() / "pickup_candidates.csv"
        weight_table = load_demand_zone_weights(weights_path)
        zone_weights = zone_sampling_weights_from_table(weight_table)
        candidates = pd.read_csv(candidates_path)
        access = candidates[candidates["accessible"] == True]  # noqa: E712
        if access.empty:
            raise RuntimeError("No accessible pickup candidates for procedural episodes")

        fleet = load_fleet_defaults()
        depot_path = fleet_dir() / "depot.json"
        if depot_path.exists():
            depot = json.loads(depot_path.read_text(encoding="utf-8"))
        else:
            # Same deterministic median-nearest rule as evaluation ensemble.
            depot_row = (
                access.assign(
                    d=(
                        (access["lat"] - access["lat"].median()) ** 2
                        + (access["lon"] - access["lon"].median()) ** 2
                    )
                )
                .sort_values("d")
                .iloc[0]
            )
            depot = {
                "label": "scenario_depot_not_observed_facility",
                "lat": float(depot_row["lat"]),
                "lon": float(depot_row["lon"]),
                "snap_node": int(depot_row["snap_node"]),
                "note": "Accessible OSM-derived depot; not a validated facility.",
            }

        graph = load_drive_graph() if load_network else None
        model = load_congestion_model() if load_network else None
        return cls(
            config=config,
            candidates=candidates,
            zone_weights=zone_weights,
            fleet=dict(fleet),
            depot=dict(depot),
            graph=graph,
            model=model,
            load_network=load_network,
        )

    def generate_requests_frame(self, regime: str, seed: int) -> pd.DataFrame:
        assert_train_seed_allowed(seed)
        if regime not in self.config["regimes"]:
            raise KeyError(f"Unknown regime {regime}")
        regime_cfg = dict(self.config["regimes"][regime])
        return generate_requests(
            self.candidates,
            self.zone_weights,
            regime,
            regime_cfg,
            self.config,
            int(seed),
        )

    def make_episode(
        self,
        *,
        regime: str,
        seed: int,
        n_vehicles: int = 3,
        master_seed: int | None = None,
        episode_index: int | None = None,
    ) -> dict:
        seed = assert_train_seed_allowed(seed)
        regime_cfg = dict(self.config["regimes"][regime])
        req_df = self.generate_requests_frame(regime, seed)
        requests = _requests_from_frame(req_df)
        fleet = dict(self.fleet)
        fleet["n_vehicles"] = int(n_vehicles)
        start_h = float(regime_cfg["start_hour"])
        horizon_h = float(regime_cfg["horizon_hours"])
        sid = f"procedural_train/{regime}_seed{seed}"
        if episode_index is not None:
            sid = f"{sid}/ep{episode_index}"
        return {
            "scenario_id": sid,
            "graph": self.graph,
            "model": self.model,
            "requests": requests,
            "fleet": fleet,
            "depot_node": int(self.depot["snap_node"]),
            "shift_start_s": start_h * 3600.0,
            "shift_end_s": (start_h + horizon_h) * 3600.0,
            "day": "Monday",
            "metadata": {
                "split": "procedural_train",
                "regime": regime,
                "seed": seed,
                "master_seed": master_seed,
                "episode_index": episode_index,
                "generator_version": self.config.get("generator_version"),
                "benchmark_version": self.config.get("benchmark_version"),
                "n_requests": len(requests),
                "train_seed_range": list(TRAIN_SEED_RANGE),
                "claim": (
                    "Synthetic geographically grounded requests for MARL training. "
                    "Not observed Casablanca customer orders. Not locked_final."
                ),
                "is_observed_order": False,
            },
        }

    def make_factory(
        self,
        *,
        master_seed: int = 0,
        n_vehicles: int = 3,
        regimes: tuple[str, ...] = REGIME_ORDER,
        curriculum: str = "round_robin",
    ) -> Callable[..., dict]:
        """Factory compatible with RaceMultiAgentEnv(scenario_factory=...).

        ``seed`` passed by the env is treated as the episode index.
        """

        def factory(seed: int = 0, n_vehicles: int = n_vehicles) -> dict:
            ep = int(seed)
            if curriculum == "round_robin":
                regime = curriculum_regime(ep, regimes)
            elif curriculum == "baseline_only":
                regime = "baseline"
            elif curriculum == "peak_only":
                regime = "peak_stress"
            elif curriculum == "tight_only":
                regime = "tight_windows"
            else:
                raise ValueError(f"Unknown curriculum {curriculum}")
            train_seed = episode_train_seed(master_seed, ep)
            self._episode_counter += 1
            return self.make_episode(
                regime=regime,
                seed=train_seed,
                n_vehicles=n_vehicles,
                master_seed=master_seed,
                episode_index=ep,
            )

        return factory


def load_protocol() -> dict:
    path = project_root() / "configs" / "marl_training_protocol.json"
    return json.loads(path.read_text(encoding="utf-8"))


def make_procedural_train_factory(
    *,
    master_seed: int = 0,
    n_vehicles: int = 3,
    curriculum: str = "round_robin",
    load_network: bool = True,
) -> tuple[ProceduralEpisodeGenerator, Callable[..., dict]]:
    gen = ProceduralEpisodeGenerator.from_release(load_network=load_network)
    return gen, gen.make_factory(
        master_seed=master_seed,
        n_vehicles=n_vehicles,
        curriculum=curriculum,
    )
