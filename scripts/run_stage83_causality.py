#!/usr/bin/env python
"""Stage 8.3 communication causality on development scenarios (non-learning + intent bridge)."""

from __future__ import annotations

import argparse
import json
import sys
from copy import deepcopy
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def _run_native(sc, graph, model, *, n_vehicles: int, delay_s: float, mode: str, seed: int = 7):
    from race_casablanca.policies import ChargingController, GreedyInsertionPolicy, RaceCooperativePolicy
    from race_casablanca.sim.environment import OnlineSimulator, SimConfig
    from race_casablanca.sim.types import RequestStatus

    reqs = deepcopy(sc.requests)
    for r in reqs:
        r.status = RequestStatus.UNRELEASED
        r.owner = None

    if mode == "greedy_charge70":
        pol = GreedyInsertionPolicy(
            charging=ChargingController(mode="charge_to_target", target_soc=0.70)
        )
        info_mode = "full"
    else:
        pol = RaceCooperativePolicy(comm_mode=mode, enable_readiness_charge=True, rng_seed=seed)
        info_mode = "restricted"

    sim = OnlineSimulator(
        scenario_id=f"{sc.scenario_id}/{mode}/d{delay_s}",
        graph=graph,
        model=model,
        requests=reqs,
        fleet={**sc.fleet, "n_vehicles": n_vehicles},
        depot_node=sc.depot_node,
        shift_start_s=sc.shift_start_s,
        shift_end_s=sc.shift_end_s,
        config=SimConfig(
            info_mode=info_mode,
            seed=0,
            initial_soc=0.35,
            n_vehicles=n_vehicles,
            message_delay_s=float(delay_s),
            packet_loss_p=0.0,
            periodic_state_broadcast=False,
            decision_on_release=True,
            day=str(getattr(sc, "day", "Monday")),
        ),
        policy=pol,
    )
    m = sim.run().to_dict()
    owners = {rid: req.owner for rid, req in sim.requests.items() if req.owner}
    n_bid_messages = float(getattr(sim, "n_bid_messages", 0) or m.get("n_bid_messages", 0) or 0)
    n_bid_bytes = float(getattr(sim, "n_bid_bytes", 0) or m.get("n_bid_bytes", 0) or 0)
    if n_bid_bytes <= 0:
        n_bid_bytes = float(getattr(pol, "n_bid_bytes_sent", 0) or 0)
    if n_bid_messages <= 0:
        n_bid_messages = float(getattr(pol, "n_messages_sent_by_policy", 0) or 0)
    method = {
        "none": "nl_none",
        "full": "nl_full",
        "selective": "nl_selective",
        "greedy_charge70": "greedy_charge70",
    }.get(mode, mode)
    return {
        "method": method,
        "delay_s": float(delay_s),
        "on_time_rate_all": float(m.get("on_time_rate_all", 0.0)),
        "n_bid_messages": n_bid_messages,
        "n_bid_bytes": n_bid_bytes,
        "n_defers_to_peer": float(getattr(pol, "n_defers_to_peer", 0) or 0),
        "n_counterfactual_decision_changes": float(
            getattr(pol, "n_counterfactual_decision_changes", 0) or 0
        ),
        "owners_json": json.dumps(owners, sort_keys=True),
    }


def _run_marl_intent(sc, graph, model, *, n_vehicles: int, ablation: str, delay_s: float = 0.0):
    from race_casablanca.marl.bc import NativeBridgeTeacher
    from race_casablanca.marl.env import RaceMultiAgentEnv
    from race_casablanca.sim.types import RequestStatus

    reqs0 = deepcopy(sc.requests)

    def factory(seed=0, n_vehicles=n_vehicles, _reqs0=reqs0, _sc=sc):
        reqs = deepcopy(_reqs0)
        for r in reqs:
            r.status = RequestStatus.UNRELEASED
            r.owner = None
        return {
            "scenario_id": _sc.scenario_id,
            "graph": graph,
            "model": model,
            "requests": reqs,
            "fleet": {**_sc.fleet, "n_vehicles": n_vehicles},
            "depot_node": _sc.depot_node,
            "shift_start_s": _sc.shift_start_s,
            "shift_end_s": _sc.shift_end_s,
            "day": getattr(_sc, "day", "Monday"),
        }

    env = RaceMultiAgentEnv(
        scenario_factory=factory,
        n_vehicles=n_vehicles,
        ablation=ablation,
        seed=0,
        max_decisions=2000,
        initial_soc=0.35,
        message_delay_s=float(delay_s),
    )
    teacher = NativeBridgeTeacher(mode="intent", comm_mode="selective")
    steps = env.reset(seed=0)
    while True:
        labels = teacher.actions(env)
        steps = env.step(labels)
        if list(steps.values())[0].done:
            break
    m = env.final_metrics()
    owners = {}
    if env.sim is not None:
        owners = {rid: req.owner for rid, req in env.sim.requests.items() if req.owner}
    return {
        "method": f"marl_intent_{ablation}",
        "delay_s": float(delay_s),
        "on_time_rate_all": float(m.get("on_time_rate_all", 0.0)),
        "n_bid_messages": float(m.get("n_bid_messages", 0) or 0),
        "n_bid_bytes": float(m.get("n_bid_bytes", 0) or 0),
        "n_defers_to_peer": 0.0,
        "n_counterfactual_decision_changes": 0.0,
        "owners_json": json.dumps(owners, sort_keys=True),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n-vehicles", type=int, default=3)
    args = parser.parse_args()

    from race_casablanca.marl.env import ABLATION_A, ABLATION_D, ABLATION_E
    from race_casablanca.marl.scenarios import resolve_eval_dirs
    from race_casablanca.paths import project_root
    from race_casablanca.sim.scenario_loader import load_congestion_model, load_drive_graph, load_scenario

    root = project_root()
    out_dir = root / "data" / "casablanca" / "online_results"
    out_dir.mkdir(parents=True, exist_ok=True)
    graph = load_drive_graph()
    model = load_congestion_model()
    paths = resolve_eval_dirs()

    rows = []
    treatments = [
        ("none", 0.0),
        ("selective", 0.0),
        ("full", 0.0),
        ("selective", 30.0),
        ("greedy_charge70", 0.0),
    ]
    for path in paths:
        sc = load_scenario(path, load_network=False, graph=graph, model=model)
        for mode, delay in treatments:
            print(f"causality {path.name} mode={mode} delay={delay}", flush=True)
            row = _run_native(sc, graph, model, n_vehicles=args.n_vehicles, delay_s=delay, mode=mode)
            row["scenario"] = path.name
            rows.append(row)
        for abl, delay in [(ABLATION_D, 0.0), (ABLATION_A, 0.0), (ABLATION_E, 0.0), (ABLATION_D, 30.0)]:
            print(f"causality {path.name} marl_intent {abl} delay={delay}", flush=True)
            row = _run_marl_intent(
                sc, graph, model, n_vehicles=args.n_vehicles, ablation=abl, delay_s=delay
            )
            row["scenario"] = path.name
            rows.append(row)

    df = pd.DataFrame(rows)
    df.to_csv(out_dir / "stage83_causality_counterfactuals.csv", index=False)

    deltas = []
    for scen, g in df.groupby("scenario"):
        base = g[(g["method"] == "nl_selective") & (g["delay_s"] == 0.0)]
        if base.empty:
            continue
        base_owners = json.loads(base.iloc[0]["owners_json"])
        base_ot = float(base.iloc[0]["on_time_rate_all"])
        for _, r in g.iterrows():
            owners = json.loads(r["owners_json"])
            keys = sorted(set(base_owners) | set(owners))
            ham = sum(1 for k in keys if base_owners.get(k) != owners.get(k))
            deltas.append(
                {
                    "scenario": scen,
                    "method": r["method"],
                    "delay_s": r["delay_s"],
                    "owner_hamming_vs_selective0": ham,
                    "ot_delta_vs_selective0": float(r["on_time_rate_all"]) - base_ot,
                    "on_time_rate_all": r["on_time_rate_all"],
                    "n_bid_bytes": r["n_bid_bytes"],
                }
            )
    ddf = pd.DataFrame(deltas)
    ddf.to_csv(out_dir / "stage83_causality_deltas.csv", index=False)
    curve = (
        df.groupby(["method", "delay_s"], as_index=False)[["on_time_rate_all", "n_bid_bytes", "n_bid_messages"]]
        .mean()
        .sort_values(["delay_s", "n_bid_bytes"])
    )
    curve.to_csv(out_dir / "stage83_service_vs_bytes.csv", index=False)
    summary = {
        "nl_ot_means": df[df["delay_s"] == 0].groupby("method")["on_time_rate_all"].mean().to_dict(),
        "selective_vs_none_ot_delta": float(
            df[(df.method == "nl_selective") & (df.delay_s == 0)]["on_time_rate_all"].mean()
            - df[(df.method == "nl_none") & (df.delay_s == 0)]["on_time_rate_all"].mean()
        ),
        "curve": curve.to_dict(orient="records"),
    }
    (out_dir / "stage83_causality_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
