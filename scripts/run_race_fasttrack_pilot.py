#!/usr/bin/env python
"""RACE-CERT fast-track pilot: same routing controller, communication treatments A–G."""

from __future__ import annotations

import argparse
import json
import sys
from copy import deepcopy
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


MODES = [
    ("A_none", "none"),
    ("B_full", "full"),
    ("C_periodic", "periodic"),
    ("D_random_matched", "random_matched"),
    ("E_selective", "selective"),
    ("F_certified", "certified"),
    ("G_learned", "learned"),
]


def run_one(sc, graph, model, *, n_vehicles: int, soc: float, delay: float, mode: str, policy):
    from race_casablanca.sim.environment import OnlineSimulator, SimConfig
    from race_casablanca.sim.types import RequestStatus

    reqs = deepcopy(sc.requests)
    for r in reqs:
        r.status = RequestStatus.UNRELEASED
        r.owner = None
    sim = OnlineSimulator(
        scenario_id=f"{sc.scenario_id}/{mode}/d{delay}",
        graph=graph,
        model=model,
        requests=reqs,
        fleet={**sc.fleet, "n_vehicles": n_vehicles},
        depot_node=sc.depot_node,
        shift_start_s=sc.shift_start_s,
        shift_end_s=sc.shift_end_s,
        config=SimConfig(
            info_mode="restricted",
            seed=0,
            initial_soc=soc,
            n_vehicles=n_vehicles,
            message_delay_s=float(delay),
            packet_loss_p=0.0,
            periodic_state_broadcast=(mode == "periodic"),
            decision_on_release=True,
            day=str(getattr(sc, "day", "Monday")),
        ),
        policy=policy,
    )
    m = sim.run().to_dict()
    owners = {rid: req.owner for rid, req in sim.requests.items() if req.owner}
    n_msgs = float(getattr(sim, "n_bid_messages", 0) or 0)
    n_bytes = float(getattr(sim, "n_bid_bytes", 0) or getattr(policy, "n_bid_bytes_sent", 0) or 0)
    if n_msgs <= 0:
        n_msgs = float(getattr(policy, "n_messages_sent_by_policy", 0) or 0)
    if n_bytes <= 0:
        n_bytes = float(getattr(policy, "n_bid_bytes_sent", 0) or 0)
    return {
        "on_time_rate_all": float(m.get("on_time_rate_all", 0.0)),
        "n_on_time": float(m.get("n_on_time", 0.0)),
        "n_served": float(m.get("n_served", 0.0)),
        "n_requests": float(m.get("n_requests", 0.0)),
        "n_bid_messages": n_msgs,
        "n_bid_bytes": n_bytes,
        "n_claims_success": float(getattr(policy, "n_claims_success", 0) or 0),
        "n_defers_to_peer": float(getattr(policy, "n_defers_to_peer", 0) or 0),
        "n_certified_resolutions": float(getattr(policy, "n_certified_resolutions", 0) or 0),
        "n_ambiguous_fallbacks": float(getattr(policy, "n_ambiguous_fallbacks", 0) or 0),
        "n_certified_suppress": float(getattr(policy, "n_certified_suppress", 0) or 0),
        "owners_json": json.dumps(owners, sort_keys=True),
        "n_reserve_violations": float(m.get("n_reserve_violations", 0) or 0),
        "n_stranded": float(m.get("n_stranded", 0) or 0),
    }


def make_policy(mode: str, *, matched_budget: int | None, learned_fn=None, seed: int = 7):
    from race_casablanca.policies.race_cert_hybrid import RaceCertHybridPolicy, make_hybrid
    from race_casablanca.policies.race_cooperative import RaceCooperativePolicy

    kwargs = dict(rng_seed=seed, enable_readiness_charge=True)
    if mode == "random_matched":
        kwargs["matched_message_budget"] = int(matched_budget or 1)
        return RaceCooperativePolicy(comm_mode="random_matched", **kwargs)
    if mode == "learned":
        return RaceCertHybridPolicy(comm_mode="learned", learned_send_fn=learned_fn, **kwargs)
    if mode == "certified":
        return RaceCertHybridPolicy(comm_mode="certified", **kwargs)
    return make_hybrid(mode, **kwargs)


def calibrate_matched_budget(paths, graph, model, n_vehicles: int, soc: float) -> int:
    """Match mean selective message count on development set (delay=0)."""

    from race_casablanca.policies.race_cooperative import RaceCooperativePolicy

    totals = []
    for path in paths:
        from race_casablanca.sim.scenario_loader import load_scenario

        sc = load_scenario(path, load_network=False, graph=graph, model=model)
        pol = RaceCooperativePolicy(comm_mode="selective", rng_seed=7, enable_readiness_charge=True)
        row = run_one(sc, graph, model, n_vehicles=n_vehicles, soc=soc, delay=0.0, mode="selective", policy=pol)
        totals.append(row["n_bid_messages"])
    return max(1, int(round(float(np.mean(totals)))))


def train_learned(paths, graph, model, n_vehicles: int, soc: float, out_dir: Path):
    from race_casablanca.coordination.learned_comm_gate import (
        collect_from_policy_rollouts,
        gate_send_fn,
        save_gate,
        train_gate_bc,
    )
    from race_casablanca.sim.scenario_loader import load_scenario

    def run_episode_fn(sc, pol, n_vehicles=n_vehicles):
        run_one(sc, graph, model, n_vehicles=n_vehicles, soc=soc, delay=0.0, mode="learned", policy=pol)

    scenarios = [load_scenario(p, load_network=False, graph=graph, model=model) for p in paths]
    X, y = collect_from_policy_rollouts(run_episode_fn, scenarios, n_vehicles=n_vehicles)
    print(f"learned BC samples={len(y)} send_rate={float(y.mean()) if len(y) else 0:.3f}", flush=True)
    if len(y) < 16:
        return None
    model_t = train_gate_bc(X, y, epochs=100)
    ckpt = out_dir / "race_cert_learned_gate.pt"
    save_gate(model_t, ckpt)
    return gate_send_fn(model_t)


def owner_hamming(a: str, b: str) -> int:
    oa, ob = json.loads(a), json.loads(b)
    keys = sorted(set(oa) | set(ob))
    return sum(1 for k in keys if oa.get(k) != ob.get(k))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n-vehicles", type=int, default=3)
    parser.add_argument("--soc", type=float, default=0.35)
    parser.add_argument("--delays", type=float, nargs="+", default=[0.0, 30.0])
    args = parser.parse_args()

    from race_casablanca.marl.scenarios import resolve_eval_dirs
    from race_casablanca.paths import project_root
    from race_casablanca.sim.scenario_loader import load_congestion_model, load_drive_graph, load_scenario

    root = project_root()
    out = root / "data" / "casablanca" / "online_results"
    out.mkdir(parents=True, exist_ok=True)
    graph = load_drive_graph()
    model = load_congestion_model()
    paths = resolve_eval_dirs()

    mb_path = out / "race_fasttrack_matched_budget.json"
    if mb_path.exists():
        matched = int(json.loads(mb_path.read_text(encoding="utf-8"))["matched_message_budget"])
        print(f"Using cached matched_message_budget={matched}", flush=True)
    else:
        print("Calibrating matched random budget from selective...", flush=True)
        matched = calibrate_matched_budget(paths, graph, model, args.n_vehicles, args.soc)
        print(f"matched_message_budget={matched}", flush=True)
        mb_path.write_text(json.dumps({"matched_message_budget": matched}, indent=2), encoding="utf-8")

    gate_path = out / "race_cert_learned_gate.pt"
    if gate_path.exists():
        print(f"Loading existing learned gate {gate_path}", flush=True)
        from race_casablanca.coordination.learned_comm_gate import gate_send_fn, load_gate

        learned_fn = gate_send_fn(load_gate(gate_path))
    else:
        print("Training lightweight learned gate (BC of selective)...", flush=True)
        learned_fn = train_learned(paths, graph, model, args.n_vehicles, args.soc, out)

    # Hybrid parity check: full hybrid vs native full on first scenario
    sc0 = load_scenario(paths[0], load_network=False, graph=graph, model=model)
    from race_casablanca.policies.race_cooperative import RaceCooperativePolicy

    native_full = run_one(
        sc0,
        graph,
        model,
        n_vehicles=args.n_vehicles,
        soc=args.soc,
        delay=0.0,
        mode="full",
        policy=RaceCooperativePolicy(comm_mode="full", rng_seed=7),
    )
    hybrid_full = run_one(
        sc0,
        graph,
        model,
        n_vehicles=args.n_vehicles,
        soc=args.soc,
        delay=0.0,
        mode="full",
        policy=make_policy("full", matched_budget=matched),
    )
    parity = {
        "scenario": paths[0].name,
        "native_full_ot": native_full["on_time_rate_all"],
        "hybrid_full_ot": hybrid_full["on_time_rate_all"],
        "ot_abs_diff": abs(native_full["on_time_rate_all"] - hybrid_full["on_time_rate_all"]),
        "owner_hamming": owner_hamming(native_full["owners_json"], hybrid_full["owners_json"]),
    }
    print("hybrid parity", parity, flush=True)
    (out / "race_fasttrack_hybrid_parity.json").write_text(json.dumps(parity, indent=2), encoding="utf-8")

    rows = []
    for path in paths:
        sc = load_scenario(path, load_network=False, graph=graph, model=model)
        for delay in args.delays:
            for label, mode in MODES:
                if mode == "learned" and learned_fn is None:
                    continue
                # Full bidding + positive delay floods the event queue (Stage 8.2 pathology).
                if mode == "full" and float(delay) > 1e-12:
                    print(f"skip {path.name} delay={delay} {label} (full+delay pathology)", flush=True)
                    continue
                # Delay>0: none / selective / certified only (learned+delay is slow and nonessential for gate).
                if float(delay) > 1e-12 and mode not in {"none", "selective", "certified"}:
                    print(f"skip {path.name} delay={delay} {label} (delay subset)", flush=True)
                    continue
                print(f"pilot {path.name} delay={delay} {label}", flush=True)
                t_ep = __import__("time").time()
                pol = make_policy(mode, matched_budget=matched, learned_fn=learned_fn)
                # periodic needs periodic_state_broadcast — handled in run_one via mode name
                row = run_one(
                    sc,
                    graph,
                    model,
                    n_vehicles=args.n_vehicles,
                    soc=args.soc,
                    delay=delay,
                    mode=mode,
                    policy=pol,
                )
                row.update(
                    {
                        "scenario": path.name,
                        "delay_s": float(delay),
                        "treatment": label,
                        "comm_mode": mode,
                        "matched_message_budget": matched,
                        "wall_s": __import__("time").time() - t_ep,
                    }
                )
                rows.append(row)
                print(
                    f"  -> OT={row['on_time_rate_all']:.3f} bytes={row['n_bid_bytes']:.0f} "
                    f"msgs={row['n_bid_messages']:.0f} wall={row['wall_s']:.1f}s",
                    flush=True,
                )
                # Incremental save for crash resilience
                pd.DataFrame(rows).to_csv(out / "race_fasttrack_pilot.csv", index=False)

    df = pd.DataFrame(rows)
    df.to_csv(out / "race_fasttrack_pilot.csv", index=False)

    # Paired deltas vs full at delay 0
    deltas = []
    for scen, g in df[df.delay_s == 0.0].groupby("scenario"):
        base = g[g.treatment == "B_full"]
        if base.empty:
            continue
        b = base.iloc[0]
        for _, r in g.iterrows():
            deltas.append(
                {
                    "scenario": scen,
                    "treatment": r["treatment"],
                    "ot_delta_vs_full": float(r["on_time_rate_all"] - b["on_time_rate_all"]),
                    "byte_ratio_vs_full": float(r["n_bid_bytes"] / b["n_bid_bytes"])
                    if b["n_bid_bytes"] > 0
                    else None,
                    "owner_hamming_vs_full": owner_hamming(b["owners_json"], r["owners_json"]),
                    "on_time_rate_all": r["on_time_rate_all"],
                    "n_bid_bytes": r["n_bid_bytes"],
                    "n_bid_messages": r["n_bid_messages"],
                }
            )
    ddf = pd.DataFrame(deltas)
    ddf.to_csv(out / "race_fasttrack_pilot_deltas.csv", index=False)

    summary = {
        "hybrid_parity": parity,
        "matched_message_budget": matched,
        "means_delay0": df[df.delay_s == 0]
        .groupby("treatment")[["on_time_rate_all", "n_bid_bytes", "n_bid_messages", "n_certified_resolutions", "n_ambiguous_fallbacks"]]
        .mean()
        .reset_index()
        .to_dict(orient="records"),
        "means_delay30": df[df.delay_s == 30]
        .groupby("treatment")[["on_time_rate_all", "n_bid_bytes", "n_bid_messages"]]
        .mean()
        .reset_index()
        .to_dict(orient="records")
        if (df.delay_s == 30).any()
        else [],
        "mean_ot_delta_vs_full_delay0": ddf.groupby("treatment")["ot_delta_vs_full"].mean().to_dict()
        if not ddf.empty
        else {},
        "mean_byte_ratio_vs_full_delay0": ddf.groupby("treatment")["byte_ratio_vs_full"].mean().to_dict()
        if not ddf.empty
        else {},
    }
    (out / "race_fasttrack_pilot_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
