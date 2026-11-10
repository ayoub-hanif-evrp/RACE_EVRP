"""Casablanca scenario factories for RACE-MARL training / evaluation.

Uses frozen geographical inputs and existing train/validation scenario files.
Does not touch locked_final / Stage-6 tuning sets for hyperparameter search.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from race_casablanca.paths import project_root, scenarios_dir
from race_casablanca.sim.scenario_loader import (
    LoadedScenario,
    load_congestion_model,
    load_drive_graph,
    load_scenario,
)
from race_casablanca.sim.types import Request, RequestStatus


TRAIN_SCENARIOS = [
    "baseline_seed1",
    "baseline_seed4",
    "baseline_seed7",
    "peak_stress_seed2",
    "peak_stress_seed5",
    "peak_stress_seed8",
    "tight_windows_seed3",
    "tight_windows_seed6",
]

VAL_SCENARIOS = [
    "peak_stress_seed101",
    "tight_windows_seed102",
]

# Compact primary matrix workloads available without regenerating the release.
WORKLOAD_ALIASES = {
    12: "baseline",
    30: "tight_windows",
    40: "peak_stress",
}


def _reset_requests(requests: list[Request]) -> list[Request]:
    out = deepcopy(requests)
    for r in out:
        r.status = RequestStatus.UNRELEASED
        r.owner = None
        r.service_start_s = None
        r.service_end_s = None
        r.on_time = None
    return out


@dataclass
class CasablancaPool:
    graph: Any
    model: Any
    scenarios: dict[str, LoadedScenario]
    names: list[str]

    def to_dict(
        self,
        name: str,
        *,
        seed: int = 0,
        n_vehicles: int | None = None,
        n_requests: int | None = None,
    ) -> dict:
        sc = self.scenarios[name]
        reqs = _reset_requests(sc.requests)
        if n_requests is not None and n_requests < len(reqs):
            # Deterministic truncation for compact scalability cells.
            rng = __import__("random").Random(seed ^ 7919)
            idx = list(range(len(reqs)))
            rng.shuffle(idx)
            reqs = [reqs[i] for i in sorted(idx[:n_requests])]
        fleet = dict(sc.fleet)
        if n_vehicles is not None:
            fleet["n_vehicles"] = int(n_vehicles)
        return {
            "scenario_id": f"{sc.scenario_id}/nv{fleet.get('n_vehicles')}/seed{seed}",
            "graph": self.graph,
            "model": self.model,
            "requests": reqs,
            "fleet": fleet,
            "depot_node": sc.depot_node,
            "shift_start_s": sc.shift_start_s,
            "shift_end_s": sc.shift_end_s,
            "day": getattr(sc, "day", "Monday"),
        }


def load_casablanca_pool(
    *,
    split: str = "train",
    names: list[str] | None = None,
) -> CasablancaPool:
    graph = load_drive_graph()
    model = load_congestion_model()
    if names is None:
        names = list(TRAIN_SCENARIOS if split == "train" else VAL_SCENARIOS)
    base = scenarios_dir() / ("train" if split == "train" else "validation")
    scenarios: dict[str, LoadedScenario] = {}
    for name in names:
        path = base / name
        if not path.exists():
            continue
        scenarios[name] = load_scenario(path, load_network=False, graph=graph, model=model)
    if not scenarios:
        raise FileNotFoundError(f"No Casablanca scenarios found under {base}")
    return CasablancaPool(graph=graph, model=model, scenarios=scenarios, names=list(scenarios.keys()))


def make_pool_factory(
    pool: CasablancaPool,
    *,
    n_vehicles: int = 3,
    n_requests: int | None = None,
    name_filter: Callable[[str], bool] | None = None,
) -> Callable[..., dict]:
    names = [n for n in pool.names if name_filter is None or name_filter(n)]
    if not names:
        names = list(pool.names)

    def factory(seed: int = 0, n_vehicles: int = n_vehicles) -> dict:
        name = names[int(seed) % len(names)]
        return pool.to_dict(name, seed=int(seed), n_vehicles=n_vehicles, n_requests=n_requests)

    return factory


def resolve_eval_dirs() -> list[Path]:
    """Validation + a few evaluation_v1 defaults (not locked_final)."""
    root = project_root()
    paths: list[Path] = []
    for name in VAL_SCENARIOS:
        p = scenarios_dir() / "validation" / name
        if p.exists():
            paths.append(p)
    ev = root / "data" / "casablanca" / "evaluation_v1" / "default"
    if ev.exists():
        # Small held-out diagnostic set (not locked_final).
        for name in (
            "peak_stress_seed1201",
            "peak_stress_seed1202",
            "tight_windows_seed1301",
            "baseline_seed1101",
        ):
            p = ev / name
            if p.exists():
                paths.append(p)
    return paths
