#!/usr/bin/env python
"""Factorial: assignment timing x peer-information handling (pre-locked-final gate).

Does not touch locked_final. Preserves historical closeout CSVs.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from copy import deepcopy
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


# Factorial arms — analyst labels
ARMS = [
    ("NONE_NOW", dict(comm_mode="none", assign_wait_mode="immediate")),
    (
        "NONE_MATCHED_WAIT",
        dict(
            comm_mode="none",
            assign_wait_mode="deadline_energy",
            force_peer_wait_schedule=True,
            max_assign_wait_s=60.0,
        ),
    ),
    (
        "H_NO_PEER",
        dict(
            comm_mode="selective",
            assign_wait_mode="deadline_energy",
            peer_trust_mode="ttl_commitment",
            ignore_peer_bids=True,
            max_assign_wait_s=60.0,
        ),
    ),
    (
        "H_CURRENT",
        dict(
            comm_mode="selective",
            assign_wait_mode="deadline_energy",
            peer_trust_mode="delay_half",
            delay_aware_trust=True,
            max_assign_wait_s=60.0,
        ),
    ),
    (
        "H_VALID_PEER",
        dict(
            comm_mode="selective",
            assign_wait_mode="deadline_energy",
            peer_trust_mode="ttl_commitment",
            max_assign_wait_s=60.0,
        ),
    ),
    (
        "SELECTIVE_LEGACY",
        dict(comm_mode="selective", assign_wait_mode="legacy", peer_trust_mode="ttl"),
    ),
    (
        "FULL_VALID_PEER",
        dict(
            comm_mode="full",
            assign_wait_mode="deadline_energy",
            peer_trust_mode="ttl_commitment",
            max_assign_wait_s=60.0,
        ),
    ),
]


def make_policy(extra: dict, *, delay: float, n_vehicles: int):
    from race_casablanca.policies.race_cooperative import RaceCooperativePolicy

    kw = dict(
        rng_seed=7,
        enable_readiness_charge=True,
        fair_physical_decisions=True,
        message_delay_s=float(delay),
        matched_n_recipients=max(1, n_vehicles - 1),
        **extra,
    )
    return RaceCooperativePolicy(**kw)


def run_one(payload: dict) -> dict:
    from race_casablanca.sim.environment import OnlineSimulator, SimConfig
    from race_casablanca.sim.scenario_loader import load_congestion_model, load_drive_graph, load_scenario
    from race_casablanca.sim.types import RequestStatus

    path = Path(payload["path"])
    label = payload["label"]
    extra = dict(payload["extra"])
    delay = float(payload["delay"])
    n_vehicles = int(payload["n_vehicles"])
    soc = float(payload["soc"])

    graph = load_drive_graph()
    model = load_congestion_model()
    sc = load_scenario(path, load_network=False, graph=graph, model=model)
    reqs = deepcopy(sc.requests)
    for r in reqs:
        r.status = RequestStatus.UNRELEASED
        r.owner = None

    policy = make_policy(extra, delay=delay, n_vehicles=n_vehicles)
    cfg = SimConfig(
        info_mode="restricted",
        seed=0,
        initial_soc=soc,
        n_vehicles=n_vehicles,
        message_delay_s=delay,
        packet_loss_p=0.0,
        decision_on_release=True,
        message_triggers_decision=True,
        day=str(getattr(sc, "day", "Monday")),
    )
    t0 = time.time()
    sim = OnlineSimulator(
        scenario_id=f"{sc.scenario_id}/{label}/d{delay}",
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
    # Delivery log summary from bus history
    n_delivered = sum(1 for msg in sim.bus.history if msg.delivered and msg.kind == "task_bid")
    ages = []
    for msg in sim.bus.history:
        if msg.kind != "task_bid" or not msg.delivered:
            continue
        as_of = float(msg.payload.get("as_of_s", msg.send_s))
        ages.append(float(msg.deliver_s) - as_of)
    return {
        "scenario": path.name,
        "treatment": label,
        "delay_s": delay,
        "on_time_rate_all": float(m.get("on_time_rate_all", 0.0)),
        "n_on_time": float(m.get("n_on_time", 0.0)),
        "n_requests": float(m.get("n_requests", 0.0)),
        "n_bid_messages": float(getattr(sim, "n_bid_messages", 0) or 0),
        "n_bid_bytes": float(getattr(sim, "n_bid_bytes", 0) or 0),
        "mean_assign_wait_s": (
            float(sim.sum_assign_wait_s) / float(sim.n_assign_windows)
            if getattr(sim, "n_assign_windows", 0)
            else 0.0
        ),
        "n_assign_deferred": float(getattr(sim, "n_assign_deferred", 0) or 0),
        "n_defers_to_peer": float(getattr(policy, "n_defers_to_peer", 0) or 0),
        "n_peer_bids_trusted": float(getattr(policy, "n_peer_bids_trusted", 0) or 0),
        "n_peer_bids_untrusted": float(getattr(policy, "n_peer_bids_untrusted", 0) or 0),
        "n_claims_ignored_stale_peer": float(getattr(policy, "n_claims_ignored_stale_peer", 0) or 0),
        "n_counterfactual_decision_changes": float(
            getattr(policy, "n_counterfactual_decision_changes", 0) or 0
        ),
        "n_wait_used_local_travel": float(getattr(policy, "n_wait_used_local_travel", 0) or 0),
        "n_physical_claim_decisions": float(getattr(policy, "n_physical_claim_decisions", 0) or 0),
        "n_task_bids_delivered": float(n_delivered),
        "mean_delivery_age_s": float(np.mean(ages)) if ages else float("nan"),
        "battery_reserve_violations": float(m.get("battery_reserve_violations", 0) or 0),
        "n_charges": float(m.get("n_charges", 0) or 0),
        "wall_s": time.time() - t0,
        "owners_json": json.dumps(owners, sort_keys=True),
    }


def owner_hamming(a: str, b: str) -> int:
    da, db = json.loads(a), json.loads(b)
    keys = set(da) | set(db)
    return sum(1 for k in keys if da.get(k) != db.get(k))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--limit-scenarios", type=int, default=0)
    parser.add_argument("--pilot-only", action="store_true", help="6 resolve_eval_dirs scenarios only")
    args = parser.parse_args()

    from race_casablanca.marl.scenarios import resolve_eval_dirs
    from race_casablanca.paths import project_root

    out = ROOT / "data" / "casablanca" / "online_results"
    out.mkdir(parents=True, exist_ok=True)

    if args.pilot_only:
        paths = resolve_eval_dirs()
    else:
        base = project_root() / "data" / "casablanca" / "evaluation_v1" / "default"
        paths = sorted([p for p in base.iterdir() if p.is_dir()])
    if args.limit_scenarios > 0:
        paths = paths[: args.limit_scenarios]

    jobs = []
    for p in paths:
        for delay in (0.0, 30.0, 120.0):
            for label, extra in ARMS:
                jobs.append(
                    {
                        "path": str(p),
                        "label": label,
                        "extra": extra,
                        "delay": delay,
                        "n_vehicles": 3,
                        "soc": 0.35,
                    }
                )

    csv_path = out / ("race_trust_factorial_pilot.csv" if args.pilot_only else "race_trust_factorial.csv")
    rows = []
    print(f"Running {len(jobs)} factorial jobs on {len(paths)} scenarios...", flush=True)
    with ProcessPoolExecutor(max_workers=max(1, args.workers)) as ex:
        futs = {ex.submit(run_one, j): j for j in jobs}
        done = 0
        for fut in as_completed(futs):
            row = fut.result()
            rows.append(row)
            done += 1
            if done % 20 == 0 or done == len(jobs):
                print(
                    f"  {done}/{len(jobs)} {row['scenario']} {row['treatment']} d={row['delay_s']} "
                    f"OT={row['on_time_rate_all']:.3f} defers={row['n_defers_to_peer']:.0f} "
                    f"trusted={row['n_peer_bids_trusted']:.0f}",
                    flush=True,
                )
                pd.DataFrame(rows).to_csv(csv_path, index=False)

    df = pd.DataFrame(rows)
    df.to_csv(csv_path, index=False)

    # Decisive contrasts
    summary = {"by_delay": {}, "decisive": {}}
    for delay, g in df.groupby("delay_s"):
        means = (
            g.groupby("treatment")[
                [
                    "on_time_rate_all",
                    "n_bid_bytes",
                    "mean_assign_wait_s",
                    "n_defers_to_peer",
                    "n_peer_bids_trusted",
                    "n_peer_bids_untrusted",
                    "n_physical_claim_decisions",
                    "n_counterfactual_decision_changes",
                ]
            ]
            .mean()
            .reset_index()
            .to_dict(orient="records")
        )
        summary["by_delay"][str(delay)] = {"means": means}

        def paired(a, b):
            aa = g[g.treatment == a].set_index("scenario")
            bb = g[g.treatment == b].set_index("scenario")
            d = (aa.on_time_rate_all - bb.on_time_rate_all).dropna()
            ham = [
                owner_hamming(aa.loc[s].owners_json, bb.loc[s].owners_json)
                for s in aa.index.intersection(bb.index)
            ]
            sem = float(d.sem()) if len(d) > 1 else 0.0
            return {
                "mean_dOT": float(d.mean()),
                "ci95": [float(d.mean() - 1.96 * sem), float(d.mean() + 1.96 * sem)],
                "wins": int((d > 1e-12).sum()),
                "ties": int((d.abs() <= 1e-12).sum()),
                "losses": int((d < -1e-12).sum()),
                "mean_owner_hamming": float(np.mean(ham)) if ham else None,
                "frac_identical_owners": float(np.mean([h == 0 for h in ham])) if ham else None,
            }

        summary["decisive"][str(delay)] = {
            "A_H_CURRENT_vs_H_NO_PEER": paired("H_CURRENT", "H_NO_PEER"),
            "B_H_CURRENT_vs_NONE_MATCHED_WAIT": paired("H_CURRENT", "NONE_MATCHED_WAIT"),
            "C_H_VALID_PEER_vs_H_NO_PEER": paired("H_VALID_PEER", "H_NO_PEER"),
            "C2_H_VALID_PEER_vs_NONE_NOW": paired("H_VALID_PEER", "NONE_NOW"),
            "D_H_VALID_PEER_vs_SELECTIVE_LEGACY": paired("H_VALID_PEER", "SELECTIVE_LEGACY"),
            "H_VALID_PEER_vs_NONE_MATCHED_WAIT": paired("H_VALID_PEER", "NONE_MATCHED_WAIT"),
        }

    sum_path = out / (
        "race_trust_factorial_pilot_summary.json"
        if args.pilot_only
        else "race_trust_factorial_summary.json"
    )
    sum_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary["decisive"], indent=2), flush=True)
    print("DONE", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
