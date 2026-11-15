#!/usr/bin/env python
"""RACE-CSC commitment-safe coordination causal development pilot (Prompt 1/5).

Six train scenarios (baseline / peak / tight). Does NOT touch locked_final.
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

# Development-calibrated fixed random comparator (bandwidth reference).
RANDOM_P_SEND = 0.25

ARMS = [
    ("A_NONE_NOW", dict(comm_mode="none", assign_wait_mode="immediate", claim_mode="legacy")),
    (
        "B_FULL_COMM",
        dict(
            comm_mode="full",
            assign_wait_mode="deadline_energy",
            peer_trust_mode="ttl_commitment",
            claim_mode="legacy",
            max_assign_wait_s=60.0,
        ),
    ),
    (
        "C_SELECTIVE_LEGACY",
        dict(
            comm_mode="selective",
            assign_wait_mode="legacy",
            peer_trust_mode="ttl",
            claim_mode="legacy",
        ),
    ),
    (
        "D_SELECTIVE_CURRENT",
        dict(
            comm_mode="selective",
            assign_wait_mode="deadline_energy",
            peer_trust_mode="ttl_commitment",
            claim_mode="legacy",
            max_assign_wait_s=60.0,
        ),
    ),
    (
        "E_MATCHED_WAIT_NO_PEER",
        dict(
            comm_mode="selective",
            assign_wait_mode="deadline_energy",
            peer_trust_mode="ttl_commitment",
            ignore_peer_bids=True,
            claim_mode="legacy",
            max_assign_wait_s=60.0,
        ),
    ),
    (
        "F_VALID_PEER_SELECTIVE",
        dict(
            comm_mode="selective",
            assign_wait_mode="deadline_energy",
            peer_trust_mode="ttl_commitment",
            claim_mode="legacy",
            max_assign_wait_s=60.0,
        ),
    ),
    (
        "G_FINAL_CANDIDATE",
        dict(
            comm_mode="selective",
            assign_wait_mode="deadline_energy",
            peer_trust_mode="ttl_commitment",
            claim_mode="csc",
            send_claim_signals=True,
            max_assign_wait_s=60.0,
            wait_authority="decentralized_signal",
        ),
    ),
    (
        "H_CANDIDATE_NO_CONFIRMATION",
        dict(
            comm_mode="selective",
            assign_wait_mode="deadline_energy",
            peer_trust_mode="ttl_commitment",
            claim_mode="csc",
            send_claim_signals=False,
            max_assign_wait_s=60.0,
            wait_authority="decentralized_signal",
        ),
    ),
    (
        "I_CANDIDATE_NO_DEADLINE_FALLBACK",
        dict(
            comm_mode="selective",
            assign_wait_mode="legacy",
            peer_trust_mode="ttl_commitment",
            claim_mode="csc",
            send_claim_signals=True,
            wait_authority="decentralized_signal",
        ),
    ),
]

PILOT_SCENARIOS = [
    "baseline_seed1",
    "baseline_seed4",
    "peak_stress_seed2",
    "peak_stress_seed5",
    "tight_windows_seed3",
    "tight_windows_seed6",
]


def make_policy(extra: dict, *, delay: float, n_vehicles: int, loss: float):
    from race_casablanca.policies.race_cooperative import RaceCooperativePolicy

    kw = dict(
        rng_seed=7,
        enable_readiness_charge=True,
        fair_physical_decisions=True,
        message_delay_s=float(delay),
        matched_n_recipients=max(1, n_vehicles - 1),
        random_p_send=RANDOM_P_SEND,
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
    loss = float(payload.get("packet_loss_p", 0.0))
    n_vehicles = int(payload["n_vehicles"])
    soc = float(payload["soc"])

    graph = load_drive_graph()
    model = load_congestion_model()
    sc = load_scenario(path, load_network=False, graph=graph, model=model)
    reqs = deepcopy(sc.requests)
    for r in reqs:
        r.status = RequestStatus.UNRELEASED
        r.owner = None

    policy = make_policy(extra, delay=delay, n_vehicles=n_vehicles, loss=loss)
    cfg = SimConfig(
        info_mode="restricted",
        seed=0,
        initial_soc=soc,
        n_vehicles=n_vehicles,
        message_delay_s=delay,
        packet_loss_p=loss,
        decision_on_release=True,
        message_triggers_decision=True,
        day=str(getattr(sc, "day", "Monday")),
    )
    t0 = time.time()
    sim = OnlineSimulator(
        scenario_id=f"{sc.scenario_id}/{label}/d{delay}/l{loss}",
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
    n_delivered = sum(1 for msg in sim.bus.history if msg.delivered and msg.kind == "task_bid")
    n_sent = sum(1 for msg in sim.bus.history if msg.kind == "task_bid")
    n_lost = sum(1 for msg in sim.bus.history if msg.kind == "task_bid" and not msg.delivered)
    n_owned_msg = sum(
        1
        for msg in sim.bus.history
        if msg.kind == "task_bid" and msg.delivered and bool(msg.payload.get("owned"))
    )
    n_intent_msg = sum(
        1
        for msg in sim.bus.history
        if msg.kind == "task_bid" and msg.delivered and bool(msg.payload.get("claim_intent"))
    )
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
        "packet_loss_p": loss,
        "n_requests": float(m.get("n_requests", 0.0)),
        "n_on_time": float(m.get("n_on_time", 0.0)),
        "n_served": float(m.get("n_served", 0.0)),
        "n_missed": float(m.get("n_missed", 0.0)),
        "n_expired": float(m.get("n_expired", 0.0)),
        "on_time_rate_all": float(m.get("on_time_rate_all", 0.0)),
        "n_late_served": float(m.get("n_served", 0.0)) - float(m.get("n_on_time", 0.0)),
        "n_claims_attempted": float(getattr(policy, "n_claims_attempted", 0) or 0),
        "n_claims_success": float(getattr(policy, "n_claims_success", 0) or 0),
        "n_claims_failed": float(
            max(
                0,
                int(getattr(policy, "n_claims_attempted", 0) or 0)
                - int(getattr(policy, "n_claims_success", 0) or 0),
            )
        ),
        "n_registry_dup_rejects": float(getattr(sim.registry, "n_rejected_duplicates", 0) or 0),
        "n_defers_to_peer": float(getattr(policy, "n_defers_to_peer", 0) or 0),
        "n_csc_defers_to_credible": float(getattr(policy, "n_csc_defers_to_credible", 0) or 0),
        "n_csc_safe_fallbacks": float(getattr(policy, "n_csc_safe_fallbacks", 0) or 0),
        "n_speculative_offers_ignored": float(getattr(policy, "n_speculative_offers_ignored", 0) or 0),
        "n_claim_intents_sent": float(getattr(policy, "n_claim_intents_sent", 0) or 0),
        "n_owned_announcements": float(getattr(policy, "n_owned_announcements", 0) or 0),
        "n_counterfactual_decision_changes": float(
            getattr(policy, "n_counterfactual_decision_changes", 0) or 0
        ),
        "n_peer_bids_trusted": float(getattr(policy, "n_peer_bids_trusted", 0) or 0),
        "n_peer_bids_untrusted": float(getattr(policy, "n_peer_bids_untrusted", 0) or 0),
        "n_bid_messages": float(getattr(sim, "n_bid_messages", 0) or 0),
        "n_bid_bytes": float(getattr(sim, "n_bid_bytes", 0) or getattr(policy, "n_bid_bytes_sent", 0) or 0),
        "n_task_bids_sent": float(n_sent),
        "n_task_bids_delivered": float(n_delivered),
        "n_task_bids_lost": float(n_lost),
        "n_owned_msgs_delivered": float(n_owned_msg),
        "n_intent_msgs_delivered": float(n_intent_msg),
        "mean_delivery_age_s": float(np.mean(ages)) if ages else float("nan"),
        "mean_assign_wait_s": (
            float(sim.sum_assign_wait_s) / float(sim.n_assign_windows)
            if getattr(sim, "n_assign_windows", 0)
            else 0.0
        ),
        "sum_assign_wait_s": float(getattr(sim, "sum_assign_wait_s", 0) or 0),
        "n_assign_deferred": float(getattr(sim, "n_assign_deferred", 0) or 0),
        "n_assign_immediate": float(getattr(sim, "n_assign_immediate", 0) or 0),
        "total_distance_m": float(m.get("total_distance_m", 0) or 0),
        "total_energy_kwh": float(m.get("total_energy_kwh", 0) or 0),
        "n_charges": float(m.get("n_charges", 0) or 0),
        "battery_reserve_violations": float(m.get("battery_reserve_violations", 0) or 0),
        "n_stranded": float(m.get("n_stranded", 0) or 0),
        "mean_decision_ms": float(m.get("mean_decision_ms", 0) or 0),
        "wall_s": time.time() - t0,
        "owners_json": json.dumps(owners, sort_keys=True),
    }


def owner_hamming(a: str, b: str) -> int:
    da, db = json.loads(a), json.loads(b)
    keys = set(da) | set(db)
    return sum(1 for k in keys if da.get(k) != db.get(k))


def summarize(df: pd.DataFrame) -> pd.DataFrame:
    keys = ["treatment", "delay_s", "packet_loss_p"]
    agg = (
        df.groupby(keys, as_index=False)
        .agg(
            n_scenarios=("scenario", "nunique"),
            mean_ot=("on_time_rate_all", "mean"),
            std_ot=("on_time_rate_all", "std"),
            mean_bytes=("n_bid_bytes", "mean"),
            mean_msgs=("n_bid_messages", "mean"),
            mean_defers=("n_defers_to_peer", "mean"),
            mean_safe_fb=("n_csc_safe_fallbacks", "mean"),
            mean_cf_changes=("n_counterfactual_decision_changes", "mean"),
            mean_spec_ignored=("n_speculative_offers_ignored", "mean"),
            mean_wait=("mean_assign_wait_s", "mean"),
            mean_energy=("total_energy_kwh", "mean"),
            mean_dist_m=("total_distance_m", "mean"),
            sum_reserve_viol=("battery_reserve_violations", "sum"),
            mean_wall_s=("wall_s", "mean"),
        )
        .sort_values(keys)
    )
    return agg


def paired_vs(df: pd.DataFrame, left: str, right: str, delay: float, loss: float = 0.0) -> dict:
    a = df[(df.treatment == left) & (df.delay_s == delay) & (df.packet_loss_p == loss)].set_index(
        "scenario"
    )
    b = df[(df.treatment == right) & (df.delay_s == delay) & (df.packet_loss_p == loss)].set_index(
        "scenario"
    )
    common = sorted(set(a.index) & set(b.index))
    if not common:
        return {"left": left, "right": right, "delay_s": delay, "n": 0}
    d_ot = a.loc[common, "on_time_rate_all"] - b.loc[common, "on_time_rate_all"]
    d_bytes = a.loc[common, "n_bid_bytes"] - b.loc[common, "n_bid_bytes"]
    hamm = [owner_hamming(a.loc[s, "owners_json"], b.loc[s, "owners_json"]) for s in common]
    return {
        "left": left,
        "right": right,
        "delay_s": delay,
        "packet_loss_p": loss,
        "n": len(common),
        "mean_delta_ot_pp": float(d_ot.mean() * 100.0),
        "std_delta_ot_pp": float(d_ot.std(ddof=1) * 100.0) if len(common) > 1 else 0.0,
        "mean_delta_bytes": float(d_bytes.mean()),
        "mean_owner_hamming": float(np.mean(hamm)),
        "n_owner_diff_scenarios": int(sum(1 for h in hamm if h > 0)),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--limit-scenarios", type=int, default=0)
    args = parser.parse_args()

    from race_casablanca.paths import scenarios_dir

    out = ROOT / "data" / "casablanca" / "online_results"
    out.mkdir(parents=True, exist_ok=True)
    cfg_path = out / "race_csc_pilot_config.json"
    raw_path = out / "race_csc_pilot.csv"
    summary_path = out / "race_csc_pilot_summary.csv"
    paired_path = out / "race_csc_pilot_paired.json"
    trace_path = out / "race_csc_pilot_event_trace_sample.json"

    paths = [scenarios_dir() / "train" / name for name in PILOT_SCENARIOS]
    paths = [p for p in paths if p.exists()]
    if args.limit_scenarios > 0:
        paths = paths[: args.limit_scenarios]

    delays = [0.0, 15.0, 30.0, 120.0]
    loss_jobs_delay = 30.0

    config = {
        "scenarios": [p.name for p in paths],
        "n_vehicles": 3,
        "initial_soc": 0.35,
        "delays_s": delays,
        "packet_loss_pilot": {"delay_s": loss_jobs_delay, "p": 0.10},
        "arms": {k: v for k, v in ARMS},
        "random_p_send": RANDOM_P_SEND,
        "locked_final_used": False,
    }
    cfg_path.write_text(json.dumps(config, indent=2), encoding="utf-8")

    jobs = []
    for p in paths:
        for delay in delays:
            for label, extra in ARMS:
                jobs.append(
                    {
                        "path": str(p),
                        "label": label,
                        "extra": extra,
                        "delay": delay,
                        "packet_loss_p": 0.0,
                        "n_vehicles": 3,
                        "soc": 0.35,
                    }
                )
        # 10% loss pilot at 30 s for key arms only
        for label, extra in ARMS:
            if label in {
                "A_NONE_NOW",
                "D_SELECTIVE_CURRENT",
                "E_MATCHED_WAIT_NO_PEER",
                "G_FINAL_CANDIDATE",
                "H_CANDIDATE_NO_CONFIRMATION",
            }:
                jobs.append(
                    {
                        "path": str(p),
                        "label": label,
                        "extra": extra,
                        "delay": loss_jobs_delay,
                        "packet_loss_p": 0.10,
                        "n_vehicles": 3,
                        "soc": 0.35,
                    }
                )

    rows = []
    print(f"CSC pilot: {len(jobs)} jobs on {len(paths)} scenarios...", flush=True)
    t_all = time.time()
    with ProcessPoolExecutor(max_workers=max(1, args.workers)) as ex:
        futs = {ex.submit(run_one, j): j for j in jobs}
        done = 0
        for fut in as_completed(futs):
            row = fut.result()
            rows.append(row)
            done += 1
            if done % 10 == 0 or done == len(jobs):
                print(
                    f"  {done}/{len(jobs)} {row['scenario']} {row['treatment']} "
                    f"d={row['delay_s']} loss={row['packet_loss_p']} "
                    f"OT={row['on_time_rate_all']:.3f} bytes={row['n_bid_bytes']:.0f} "
                    f"safe_fb={row['n_csc_safe_fallbacks']:.0f}",
                    flush=True,
                )
                pd.DataFrame(rows).to_csv(raw_path, index=False)

    df = pd.DataFrame(rows)
    df.to_csv(raw_path, index=False)
    summary = summarize(df)
    summary.to_csv(summary_path, index=False)

    paired = []
    for delay in delays:
        for left, right in [
            ("G_FINAL_CANDIDATE", "A_NONE_NOW"),
            ("G_FINAL_CANDIDATE", "E_MATCHED_WAIT_NO_PEER"),
            ("G_FINAL_CANDIDATE", "D_SELECTIVE_CURRENT"),
            ("G_FINAL_CANDIDATE", "B_FULL_COMM"),
            ("G_FINAL_CANDIDATE", "F_VALID_PEER_SELECTIVE"),
            ("G_FINAL_CANDIDATE", "H_CANDIDATE_NO_CONFIRMATION"),
            ("G_FINAL_CANDIDATE", "I_CANDIDATE_NO_DEADLINE_FALLBACK"),
            ("D_SELECTIVE_CURRENT", "E_MATCHED_WAIT_NO_PEER"),
            ("H_CANDIDATE_NO_CONFIRMATION", "E_MATCHED_WAIT_NO_PEER"),
            ("B_FULL_COMM", "A_NONE_NOW"),
        ]:
            paired.append(paired_vs(df, left, right, delay))
    paired.append(paired_vs(df, "G_FINAL_CANDIDATE", "E_MATCHED_WAIT_NO_PEER", 30.0, 0.10))
    paired_path.write_text(json.dumps(paired, indent=2), encoding="utf-8")

    # Representative ownership/comm counters for one scenario
    sample = df[(df.scenario == paths[0].name) & (df.packet_loss_p == 0.0) & (df.delay_s == 30.0)]
    trace_path.write_text(
        json.dumps(
            {
                "scenario": paths[0].name,
                "delay_s": 30.0,
                "rows": sample.to_dict(orient="records"),
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    print("\n=== CSC PILOT SUMMARY (loss=0) ===", flush=True)
    print(summary[summary.packet_loss_p == 0.0].to_string(index=False), flush=True)
    print(f"\nWrote {raw_path}", flush=True)
    print(f"Wrote {summary_path}", flush=True)
    print(f"Wrote {paired_path}", flush=True)
    print(f"Total wall_s={time.time() - t_all:.1f}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
