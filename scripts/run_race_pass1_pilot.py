#!/usr/bin/env python
"""PASS1 development pilot: fair A–G communication with fixed native routing."""

from __future__ import annotations

import argparse
import json
import sys
import time
from copy import deepcopy
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


TREATMENTS = [
    ("A_none", "none"),
    ("B_full", "full"),
    ("C_periodic", "periodic"),
    ("D_random_matched", "random_matched"),
    ("E_selective", "selective"),
    ("F_certified", "certified"),
    ("G_ecom", "ecom"),
]


def run_one(sc, graph, model, *, n_vehicles, soc, delay, packet_loss, mode, policy, period_s=300.0):
    from race_casablanca.sim.environment import OnlineSimulator, SimConfig
    from race_casablanca.sim.types import RequestStatus

    reqs = deepcopy(sc.requests)
    for r in reqs:
        r.status = RequestStatus.UNRELEASED
        r.owner = None
    # Update matched controller recipient count if present
    if hasattr(policy, "_matched") and policy._matched is not None:
        policy._matched.n_recipients = max(1, n_vehicles - 1)
    cfg = SimConfig(
        info_mode="restricted",
        seed=0,
        initial_soc=soc,
        n_vehicles=n_vehicles,
        message_delay_s=float(delay),
        packet_loss_p=float(packet_loss),
        packet_loss_seed=0,
        periodic_broadcast_s=float(period_s) if mode == "periodic" else 0.0,
        periodic_state_broadcast=False,  # task-bid periodic decisions, no state floods
        message_triggers_decision=True,
        decision_on_release=True,
        day=str(getattr(sc, "day", "Monday")),
    )
    sim = OnlineSimulator(
        scenario_id=f"{sc.scenario_id}/{mode}/d{delay}",
        graph=graph,
        model=model,
        requests=reqs,
        fleet={**sc.fleet, "n_vehicles": n_vehicles},
        depot_node=sc.depot_node,
        shift_start_s=sc.shift_start_s,
        shift_end_s=sc.shift_end_s,
        config=cfg,
        policy=policy,
    )
    m = sim.run().to_dict()
    owners = {rid: req.owner for rid, req in sim.requests.items() if req.owner}
    return {
        "on_time_rate_all": float(m.get("on_time_rate_all", 0.0)),
        "n_on_time": float(m.get("n_on_time", 0.0)),
        "n_served": float(m.get("n_served", 0.0)),
        "n_requests": float(m.get("n_requests", 0.0)),
        "n_bid_messages": float(getattr(sim, "n_bid_messages", 0) or 0),
        "n_bid_bytes": float(getattr(sim, "n_bid_bytes", 0) or 0),
        "n_state_broadcast_messages": float(getattr(sim, "n_state_broadcast_messages", 0) or 0),
        "n_bid_delivers_superseded": float(getattr(sim, "n_bid_delivers_superseded", 0) or 0),
        "n_bid_delivers_coalesced": float(getattr(sim, "n_bid_delivers_coalesced", 0) or 0),
        "policy_msgs": float(getattr(policy, "n_messages_sent_by_policy", 0) or 0),
        "n_ecom_proved": float(getattr(policy, "n_ecom_proved", 0) or 0),
        "n_ecom_heuristic": float(getattr(policy, "n_ecom_heuristic", 0) or 0),
        "n_ecom_fallback": float(getattr(policy, "n_ecom_fallback", 0) or 0),
        "n_certified_resolutions": float(getattr(policy, "n_certified_resolutions", 0) or 0),
        "n_certified_suppress": float(getattr(policy, "n_certified_suppress", 0) or 0),
        "owners_json": json.dumps(owners, sort_keys=True),
    }


def make_policy(mode, *, matched_msgs, n_vehicles, seed=7):
    from race_casablanca.policies.race_cert_hybrid import make_hybrid
    from race_casablanca.policies.race_cooperative import RaceCooperativePolicy

    kw = dict(rng_seed=seed, enable_readiness_charge=True, matched_n_recipients=max(1, n_vehicles - 1))
    if mode == "random_matched":
        return RaceCooperativePolicy(
            comm_mode="random_matched", matched_message_budget=int(matched_msgs), **kw
        )
    return make_hybrid(mode, **kw)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n-vehicles", type=int, default=3)
    parser.add_argument("--soc", type=float, default=0.35)
    parser.add_argument("--delays", type=float, nargs="+", default=[0.0, 30.0, 120.0])
    parser.add_argument("--packet-loss", type=float, default=0.0)
    args = parser.parse_args()

    from race_casablanca.marl.scenarios import resolve_eval_dirs
    from race_casablanca.paths import project_root
    from race_casablanca.policies.race_cooperative import RaceCooperativePolicy
    from race_casablanca.sim.scenario_loader import load_congestion_model, load_drive_graph, load_scenario

    root = project_root()
    out = root / "data" / "casablanca" / "online_results"
    out.mkdir(parents=True, exist_ok=True)
    graph = load_drive_graph()
    model = load_congestion_model()
    paths = resolve_eval_dirs()

    # Calibrate matched recipient budget from selective (delay=0) on development set
    sel_msgs = []
    sel_bytes = []
    for path in paths:
        sc = load_scenario(path, load_network=False, graph=graph, model=model)
        pol = RaceCooperativePolicy(comm_mode="selective", rng_seed=7)
        row = run_one(
            sc, graph, model, n_vehicles=args.n_vehicles, soc=args.soc, delay=0.0,
            packet_loss=0.0, mode="selective", policy=pol,
        )
        sel_msgs.append(row["n_bid_messages"])
        sel_bytes.append(row["n_bid_bytes"])
    matched_msgs = max(1, int(round(float(np.mean(sel_msgs)))))
    matched_bytes = float(np.mean(sel_bytes))
    print(f"matched recipient msgs={matched_msgs} mean selective bytes={matched_bytes:.1f}", flush=True)
    (out / "race_pass1_matched_budget.json").write_text(
        json.dumps({"matched_recipient_messages": matched_msgs, "matched_bytes": matched_bytes}, indent=2),
        encoding="utf-8",
    )

    rows = []
    for path in paths:
        sc = load_scenario(path, load_network=False, graph=graph, model=model)
        for delay in args.delays:
            for label, mode in TREATMENTS:
                # Packet-loss stress only on primary delay 30 for speed
                losses = [0.0]
                if abs(delay - 30.0) < 1e-9:
                    losses = [0.0, 0.1] if args.packet_loss > 0 else [0.0, 0.1]
                for ploss in losses:
                    if delay not in (0.0, 30.0) and mode not in {"none", "full", "selective", "ecom"}:
                        continue
                    if ploss > 0 and mode not in {"full", "selective", "ecom"}:
                        continue
                    print(f"PASS1 {path.name} d={delay} loss={ploss} {label}", flush=True)
                    t0 = time.time()
                    pol = make_policy(mode, matched_msgs=matched_msgs, n_vehicles=args.n_vehicles)
                    row = run_one(
                        sc, graph, model, n_vehicles=args.n_vehicles, soc=args.soc,
                        delay=delay, packet_loss=ploss, mode=mode, policy=pol,
                    )
                    row.update(
                        {
                            "scenario": path.name,
                            "delay_s": float(delay),
                            "packet_loss_p": float(ploss),
                            "treatment": label,
                            "comm_mode": mode,
                            "wall_s": time.time() - t0,
                        }
                    )
                    rows.append(row)
                    print(
                        f"  OT={row['on_time_rate_all']:.3f} msgs={row['n_bid_messages']:.0f} "
                        f"bytes={row['n_bid_bytes']:.0f} wall={row['wall_s']:.1f}s",
                        flush=True,
                    )
                    pd.DataFrame(rows).to_csv(out / "race_pass1_pilot.csv", index=False)

    df = pd.DataFrame(rows)
    df.to_csv(out / "race_pass1_pilot.csv", index=False)

    def means(sub):
        return (
            sub.groupby("treatment")[["on_time_rate_all", "n_bid_messages", "n_bid_bytes"]]
            .agg(["mean", "std"])
            .reset_index()
        )

    d0 = df[(df.delay_s == 0) & (df.packet_loss_p == 0)]
    summary = {
        "matched_recipient_messages": matched_msgs,
        "matched_bytes_from_selective": matched_bytes,
        "means_delay0": d0.groupby("treatment")[
            ["on_time_rate_all", "n_bid_messages", "n_bid_bytes", "n_ecom_proved", "n_ecom_fallback"]
        ]
        .mean()
        .reset_index()
        .to_dict(orient="records"),
        "means_delay30": df[(df.delay_s == 30) & (df.packet_loss_p == 0)]
        .groupby("treatment")[["on_time_rate_all", "n_bid_messages", "n_bid_bytes"]]
        .mean()
        .reset_index()
        .to_dict(orient="records"),
        "means_delay120": df[(df.delay_s == 120) & (df.packet_loss_p == 0)]
        .groupby("treatment")[["on_time_rate_all", "n_bid_messages", "n_bid_bytes"]]
        .mean()
        .reset_index()
        .to_dict(orient="records"),
        "byte_ratio_mean_of_ratios": {},
        "ratio_of_mean_bytes": {},
    }
    if not d0.empty and (d0.treatment == "B_full").any():
        full_bytes = float(d0[d0.treatment == "B_full"]["n_bid_bytes"].mean())
        for t, g in d0.groupby("treatment"):
            mb = float(g["n_bid_bytes"].mean())
            summary["ratio_of_mean_bytes"][t] = mb / full_bytes if full_bytes > 0 else None
            # mean of scenario-level ratios
            ratios = []
            for scen, sg in d0.groupby("scenario"):
                fb = sg[sg.treatment == "B_full"]
                tb = sg[sg.treatment == t]
                if len(fb) and len(tb) and float(fb.iloc[0]["n_bid_bytes"]) > 0:
                    ratios.append(float(tb.iloc[0]["n_bid_bytes"]) / float(fb.iloc[0]["n_bid_bytes"]))
            summary["byte_ratio_mean_of_ratios"][t] = float(np.mean(ratios)) if ratios else None

    (out / "race_pass1_pilot_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
