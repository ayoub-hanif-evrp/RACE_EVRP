#!/usr/bin/env python
"""Stage 8.2 follow-up: message causality counterfactuals + service-vs-byte curve.

Runs non-learning RaceCooperativePolicy under matched exogenous conditions:
  - full / selective / none / withheld (none) / delayed
Reports assignment/OT deltas and a service-versus-byte table.
Does NOT feed counterfactual outcomes into any learner.
"""

from __future__ import annotations

import argparse
import json
import sys
from copy import deepcopy
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def _run_one(sc, graph, model, *, n_vehicles: int, delay_s: float, mode: str, seed: int = 7):
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
        comm_mode = None
    else:
        pol = RaceCooperativePolicy(
            comm_mode=mode, enable_readiness_charge=True, rng_seed=seed
        )
        info_mode = "restricted"
        comm_mode = mode

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
    owners = {}
    for rid, req in sim.requests.items():
        if req.owner:
            owners[rid] = req.owner
    # Prefer live simulator / policy counters (EpisodeMetrics may omit bid traffic).
    n_bid_messages = float(getattr(sim, "n_bid_messages", 0) or m.get("n_bid_messages", 0) or 0)
    n_bid_bytes = float(getattr(sim, "n_bid_bytes", 0) or m.get("n_bid_bytes", 0) or 0)
    if n_bid_bytes <= 0:
        n_bid_bytes = float(getattr(pol, "n_bid_bytes_sent", 0) or 0)
    if n_bid_messages <= 0:
        n_bid_messages = float(getattr(pol, "n_messages_sent_by_policy", 0) or 0)
    out = {
        "method": mode if mode != "none" else "nl_none",
        "delay_s": float(delay_s),
        "on_time_rate_all": float(m.get("on_time_rate_all", 0.0)),
        "n_on_time": float(m.get("n_on_time", 0.0)),
        "n_served": float(m.get("n_served", 0.0)),
        "n_requests": float(m.get("n_requests", 0.0)),
        "n_bid_messages": n_bid_messages,
        "n_bid_bytes": n_bid_bytes,
        "policy_msgs": float(getattr(pol, "n_messages_sent_by_policy", 0) or 0),
        "n_counterfactual_decision_changes": float(
            getattr(pol, "n_counterfactual_decision_changes", 0) or 0
        ),
        "n_defers_to_peer": float(getattr(pol, "n_defers_to_peer", 0) or 0),
        "owners_json": json.dumps(owners, sort_keys=True),
    }
    if mode == "greedy_charge70":
        out["method"] = "greedy_charge70"
    elif mode == "full":
        out["method"] = "nl_full"
    elif mode == "selective":
        out["method"] = "nl_selective"
    elif mode == "none":
        out["method"] = "nl_none"
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n-vehicles", type=int, default=3)
    parser.add_argument("--out-dir", default="data/casablanca/online_results")
    args = parser.parse_args()

    from race_casablanca.marl.scenarios import resolve_eval_dirs
    from race_casablanca.paths import project_root
    from race_casablanca.sim.scenario_loader import load_congestion_model, load_drive_graph, load_scenario

    root = project_root()
    out_dir = root / args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    print("Loading network...", flush=True)
    graph = load_drive_graph()
    model = load_congestion_model()
    paths = resolve_eval_dirs()
    if not paths:
        raise SystemExit("No eval scenarios")

    rows = []
    # Treatments: none (withheld), selective, full, selective@30s delay, greedy
    treatments = [
        ("none", 0.0),
        ("selective", 0.0),
        ("full", 0.0),
        ("selective", 30.0),  # delayed certificates
        ("greedy_charge70", 0.0),
    ]
    for path in paths:
        sc = load_scenario(path, load_network=False, graph=graph, model=model)
        for mode, delay in treatments:
            if mode == "full" and delay > 0:
                continue  # known event-queue pathology
            print(f"causality {path.name} mode={mode} delay={delay}", flush=True)
            row = _run_one(sc, graph, model, n_vehicles=args.n_vehicles, delay_s=delay, mode=mode)
            row["scenario"] = path.name
            rows.append(row)

    df = pd.DataFrame(rows)
    df.to_csv(out_dir / "stage82_causality_counterfactuals.csv", index=False)

    # Assignment Hamming distance vs selective@0 (matched exogenous scenario)
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
                    "n_defers_to_peer": r["n_defers_to_peer"],
                    "n_counterfactual_decision_changes": r["n_counterfactual_decision_changes"],
                }
            )
    ddf = pd.DataFrame(deltas)
    ddf.to_csv(out_dir / "stage82_causality_deltas.csv", index=False)

    # Service-versus-byte curve (aggregate means)
    curve = (
        df.groupby(["method", "delay_s"], as_index=False)[
            ["on_time_rate_all", "n_bid_bytes", "n_bid_messages", "n_served", "n_defers_to_peer"]
        ]
        .mean()
        .sort_values(["delay_s", "n_bid_bytes"])
    )
    curve.to_csv(out_dir / "stage82_service_vs_bytes.csv", index=False)

    # Merge learned eval if present
    learned_path = out_dir / "stage82_learned_eval.csv"
    if learned_path.exists():
        ldf = pd.read_csv(learned_path)
        # Expect columns include on_time_rate_all, n_bid_messages / bytes if evaluate wrote them
        cols = [c for c in ["ablation", "seed", "on_time_rate_all", "n_bid_messages", "n_bid_bytes", "scenario"] if c in ldf.columns]
        if "ablation" in ldf.columns and "on_time_rate_all" in ldf.columns:
            lg = ldf.groupby("ablation", as_index=False).agg(
                on_time_rate_all=("on_time_rate_all", "mean"),
                n_bid_bytes=("n_bid_bytes", "mean") if "n_bid_bytes" in ldf.columns else ("on_time_rate_all", "size"),
                n_bid_messages=("n_bid_messages", "mean") if "n_bid_messages" in ldf.columns else ("on_time_rate_all", "size"),
            )
            lg["family"] = "learned"
            lg.to_csv(out_dir / "stage82_learned_service_bytes.csv", index=False)

    summary = {
        "n_scenario_rows": len(df),
        "nl_ot_means": df[df["delay_s"] == 0].groupby("method")["on_time_rate_all"].mean().to_dict(),
        "selective_vs_none_ot_delta": float(
            df[(df.method == "nl_selective") & (df.delay_s == 0)]["on_time_rate_all"].mean()
            - df[(df.method == "nl_none") & (df.delay_s == 0)]["on_time_rate_all"].mean()
        ),
        "selective_delay30_ot": float(
            df[(df.method == "nl_selective") & (df.delay_s == 30)]["on_time_rate_all"].mean()
        )
        if ((df.method == "nl_selective") & (df.delay_s == 30)).any()
        else None,
        "mean_owner_hamming_none_vs_sel": float(
            ddf[(ddf.method == "nl_none") & (ddf.delay_s == 0)]["owner_hamming_vs_selective0"].mean()
        )
        if not ddf.empty
        else None,
        "curve": curve.to_dict(orient="records"),
    }
    (out_dir / "stage82_causality_bytes_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2), flush=True)
    print("PASS causality + service-vs-byte artifacts written", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
