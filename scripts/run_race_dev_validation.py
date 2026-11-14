#!/usr/bin/env python
"""Bounded PASS-1 follow-up: delay diagnosis + 60-scenario development validation.

Does NOT touch locked_final. Calibrates matched budgets on train/dev only.
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


def default_dev_dirs() -> list[Path]:
    from race_casablanca.paths import project_root

    root = project_root()
    base = root / "data" / "casablanca" / "evaluation_v1" / "default"
    return sorted([p for p in base.iterdir() if p.is_dir()])


def make_policy(mode: str, *, matched_msgs: int, matched_bytes: float, n_vehicles: int, delay: float):
    from race_casablanca.policies.race_cert_hybrid import make_hybrid
    from race_casablanca.policies.race_cooperative import RaceCooperativePolicy

    kw = dict(
        rng_seed=7,
        enable_readiness_charge=True,
        matched_n_recipients=max(1, n_vehicles - 1),
        message_delay_s=float(delay),
    )
    if mode == "random_matched":
        return RaceCooperativePolicy(
            comm_mode="random_matched", matched_message_budget=int(matched_msgs), **kw
        )
    if mode == "random_matched_bytes":
        return RaceCooperativePolicy(
            comm_mode="random_matched_bytes",
            matched_byte_budget=float(matched_bytes),
            typical_payload_bytes=max(200.0, matched_bytes / max(1, matched_msgs)),
            **kw,
        )
    if mode == "selective_deadline":
        return RaceCooperativePolicy(
            comm_mode="selective",
            assign_wait_mode="deadline_energy",
            delay_aware_trust=True,
            max_assign_wait_s=60.0,
            **kw,
        )
    if mode == "ecom_deadline":
        return make_hybrid(
            "ecom",
            assign_wait_mode="deadline_energy",
            delay_aware_trust=True,
            max_assign_wait_s=60.0,
            **kw,
        )
    if mode in {"certified", "ecom"}:
        return make_hybrid(mode, **kw)
    return RaceCooperativePolicy(comm_mode=mode, **kw)


def run_one(payload: dict) -> dict:
    from race_casablanca.sim.environment import OnlineSimulator, SimConfig
    from race_casablanca.sim.scenario_loader import load_congestion_model, load_drive_graph, load_scenario
    from race_casablanca.sim.types import RequestStatus

    path = Path(payload["path"])
    mode = payload["mode"]
    label = payload["label"]
    delay = float(payload["delay"])
    n_vehicles = int(payload["n_vehicles"])
    soc = float(payload["soc"])
    matched_msgs = int(payload["matched_msgs"])
    matched_bytes = float(payload["matched_bytes"])
    packet_loss = float(payload.get("packet_loss", 0.0))

    graph = load_drive_graph()
    model = load_congestion_model()
    sc = load_scenario(path, load_network=False, graph=graph, model=model)
    reqs = deepcopy(sc.requests)
    for r in reqs:
        r.status = RequestStatus.UNRELEASED
        r.owner = None

    policy = make_policy(
        mode,
        matched_msgs=matched_msgs,
        matched_bytes=matched_bytes,
        n_vehicles=n_vehicles,
        delay=delay,
    )
    if hasattr(policy, "_matched") and policy._matched is not None:
        policy._matched.n_recipients = max(1, n_vehicles - 1)
    if hasattr(policy, "_matched_bytes") and policy._matched_bytes is not None:
        policy._matched_bytes.n_recipients = max(1, n_vehicles - 1)

    cfg = SimConfig(
        info_mode="restricted",
        seed=0,
        initial_soc=soc,
        n_vehicles=n_vehicles,
        message_delay_s=delay,
        packet_loss_p=packet_loss,
        packet_loss_seed=0,
        periodic_broadcast_s=300.0 if mode == "periodic" else 0.0,
        periodic_state_broadcast=False,
        message_triggers_decision=True,
        decision_on_release=True,
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
    wall = time.time() - t0

    # Bids present at end are not assign-time; use assign counters + deferrals.
    owners = {rid: req.owner for rid, req in sim.requests.items() if req.owner}
    idle_s = float(sum(getattr(v, "total_wait_s", 0.0) for v in sim.vehicles.values()))
    return {
        "scenario": path.name,
        "treatment": label,
        "comm_mode": mode,
        "delay_s": delay,
        "packet_loss_p": packet_loss,
        "n_vehicles": n_vehicles,
        "soc": soc,
        "on_time_rate_all": float(m.get("on_time_rate_all", 0.0)),
        "n_on_time": float(m.get("n_on_time", 0.0)),
        "n_served": float(m.get("n_served", 0.0)),
        "n_requests": float(m.get("n_requests", 0.0)),
        "n_missed": float(m.get("n_missed", 0.0)),
        "n_expired": float(m.get("n_expired", 0.0)),
        "n_bid_messages": float(getattr(sim, "n_bid_messages", 0) or 0),
        "n_bid_bytes": float(getattr(sim, "n_bid_bytes", 0) or 0),
        "n_assign_windows": float(getattr(sim, "n_assign_windows", 0) or 0),
        "n_assign_immediate": float(getattr(sim, "n_assign_immediate", 0) or 0),
        "n_assign_deferred": float(getattr(sim, "n_assign_deferred", 0) or 0),
        "sum_assign_wait_s": float(getattr(sim, "sum_assign_wait_s", 0.0) or 0.0),
        "max_assign_wait_s": float(getattr(sim, "max_assign_wait_s", 0.0) or 0.0),
        "mean_assign_wait_s": (
            float(sim.sum_assign_wait_s) / float(sim.n_assign_windows)
            if getattr(sim, "n_assign_windows", 0)
            else 0.0
        ),
        "vehicle_idle_wait_s": idle_s,
        "n_defers_to_peer": float(getattr(policy, "n_defers_to_peer", 0) or 0),
        "n_claims_success": float(getattr(policy, "n_claims_success", 0) or 0),
        "n_claims_ignored_stale_peer": float(getattr(policy, "n_claims_ignored_stale_peer", 0) or 0),
        "n_ecom_proved": float(getattr(policy, "n_ecom_proved", 0) or 0),
        "n_ecom_fallback": float(getattr(policy, "n_ecom_fallback", 0) or 0),
        "n_certified_resolutions": float(getattr(policy, "n_certified_resolutions", 0) or 0),
        "battery_reserve_violations": float(m.get("battery_reserve_violations", 0) or 0),
        "battery_exhaustion": float(m.get("battery_exhaustion", 0) or 0),
        "n_charges": float(m.get("n_charges", 0) or 0),
        "charge_duration_s": float(m.get("charge_duration_s", 0) or 0),
        "mean_decision_runtime_s": float(m.get("mean_decision_runtime_s", 0) or 0),
        "wall_s": wall,
        "owners_json": json.dumps(owners, sort_keys=True),
    }


def calibrate_budgets(paths: list[Path], *, n_vehicles: int, soc: float) -> tuple[int, float]:
    jobs = [
        {
            "path": str(p),
            "mode": "selective",
            "label": "E_selective",
            "delay": 0.0,
            "n_vehicles": n_vehicles,
            "soc": soc,
            "matched_msgs": 10**9,
            "matched_bytes": 1e18,
        }
        for p in paths
    ]
    rows = [run_one(j) for j in jobs]
    msgs = max(1, int(round(float(np.mean([r["n_bid_messages"] for r in rows])))))
    nbytes = float(np.mean([r["n_bid_bytes"] for r in rows]))
    return msgs, nbytes


def summarize(df: pd.DataFrame) -> dict:
    out: dict = {"by_delay": {}}
    for delay, g in df.groupby("delay_s"):
        means = (
            g.groupby("treatment")[
                [
                    "on_time_rate_all",
                    "n_bid_messages",
                    "n_bid_bytes",
                    "mean_assign_wait_s",
                    "n_assign_deferred",
                    "n_defers_to_peer",
                    "n_ecom_proved",
                    "battery_reserve_violations",
                    "wall_s",
                ]
            ]
            .mean()
            .reset_index()
        )
        # paired vs selective
        paired = {}
        if (g.treatment == "E_selective").any():
            sel = g[g.treatment == "E_selective"].set_index("scenario")
            for t, tg in g.groupby("treatment"):
                o = tg.set_index("scenario")
                d = o["on_time_rate_all"] - sel["on_time_rate_all"]
                d = d.dropna()
                if len(d) == 0:
                    continue
                paired[t] = {
                    "n": int(len(d)),
                    "mean_dOT": float(d.mean()),
                    "ci95": [float(d.mean() - 1.96 * d.sem()), float(d.mean() + 1.96 * d.sem())]
                    if len(d) > 1 and d.sem() == d.sem()
                    else [None, None],
                    "wins": int((d > 1e-12).sum()),
                    "ties": int((d.abs() <= 1e-12).sum()),
                    "losses": int((d < -1e-12).sum()),
                    "mean_byte_ratio_vs_sel": float((o["n_bid_bytes"] / sel["n_bid_bytes"].replace(0, np.nan)).mean()),
                }
        out["by_delay"][str(delay)] = {
            "means": means.to_dict(orient="records"),
            "paired_vs_selective": paired,
        }
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["diagnosis", "expanded", "both"], default="both")
    parser.add_argument("--n-vehicles", type=int, default=3)
    parser.add_argument("--soc", type=float, default=0.35)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--limit-scenarios", type=int, default=0)
    args = parser.parse_args()

    from race_casablanca.marl.scenarios import resolve_eval_dirs

    out = ROOT / "data" / "casablanca" / "online_results"
    out.mkdir(parents=True, exist_ok=True)

    diag_paths = resolve_eval_dirs()
    exp_paths = default_dev_dirs()
    if args.limit_scenarios > 0:
        exp_paths = exp_paths[: args.limit_scenarios]
        diag_paths = diag_paths[: min(args.limit_scenarios, len(diag_paths))]

    # Pre-register noninferiority margin BEFORE expanded evaluation.
    noninf = {
        "primary_metric": "on_time_rate_all",
        "comparator": "E_selective",
        "margin_absolute_ot": 0.02,
        "rationale": "2 percentage points OT ≈ 0.64 requests per 32-request episode; practical ops tolerance before claiming noninferior service at lower bytes.",
        "frozen_before_expanded_eval": True,
    }
    (out / "race_devval_noninferiority_margin.json").write_text(json.dumps(noninf, indent=2), encoding="utf-8")

    # Calibrate on train scenarios (delay 0 selective), never locked_final.
    from race_casablanca.paths import scenarios_dir

    train_paths = sorted((scenarios_dir() / "train").iterdir())
    train_paths = [p for p in train_paths if p.is_dir()][:8]
    print(f"Calibrating matched budgets on {len(train_paths)} train scenarios...", flush=True)
    matched_msgs, matched_bytes = calibrate_budgets(train_paths, n_vehicles=args.n_vehicles, soc=args.soc)
    print(f"matched_msgs={matched_msgs} matched_bytes={matched_bytes:.1f}", flush=True)
    (out / "race_devval_matched_budget.json").write_text(
        json.dumps({"matched_recipient_messages": matched_msgs, "matched_bytes": matched_bytes}, indent=2),
        encoding="utf-8",
    )

    def build_jobs(paths, delays, treatments, packet_loss_at_30=False):
        jobs = []
        for p in paths:
            for delay in delays:
                losses = [0.0]
                if packet_loss_at_30 and abs(delay - 30.0) < 1e-9:
                    losses = [0.0, 0.1]
                for ploss in losses:
                    for label, mode in treatments:
                        if ploss > 0 and mode not in {"full", "selective", "ecom", "ecom_deadline", "selective_deadline"}:
                            continue
                        jobs.append(
                            {
                                "path": str(p),
                                "mode": mode,
                                "label": label,
                                "delay": float(delay),
                                "n_vehicles": args.n_vehicles,
                                "soc": args.soc,
                                "matched_msgs": matched_msgs,
                                "matched_bytes": matched_bytes,
                                "packet_loss": float(ploss),
                            }
                        )
        return jobs

    def execute(jobs, csv_name, summary_name):
        rows = []
        csv_path = out / csv_name
        print(f"Running {len(jobs)} jobs with {args.workers} workers -> {csv_path}", flush=True)
        if args.workers <= 1:
            for j in jobs:
                row = run_one(j)
                rows.append(row)
                print(
                    f"  {row['scenario']} d={row['delay_s']} {row['treatment']} "
                    f"OT={row['on_time_rate_all']:.3f} wait={row['mean_assign_wait_s']:.1f} "
                    f"bytes={row['n_bid_bytes']:.0f}",
                    flush=True,
                )
                pd.DataFrame(rows).to_csv(csv_path, index=False)
        else:
            with ProcessPoolExecutor(max_workers=args.workers) as ex:
                futs = {ex.submit(run_one, j): j for j in jobs}
                done = 0
                for fut in as_completed(futs):
                    row = fut.result()
                    rows.append(row)
                    done += 1
                    if done % 10 == 0 or done == len(jobs):
                        print(f"  progress {done}/{len(jobs)} last={row['scenario']}/{row['treatment']}", flush=True)
                        pd.DataFrame(rows).to_csv(csv_path, index=False)
        df = pd.DataFrame(rows)
        df.to_csv(csv_path, index=False)
        summary = summarize(df)
        summary["noninferiority_margin"] = noninf
        summary["matched_budget"] = {"msgs": matched_msgs, "bytes": matched_bytes}
        (out / summary_name).write_text(json.dumps(summary, indent=2), encoding="utf-8")
        return df, summary

    if args.mode in {"diagnosis", "both"}:
        diag_treatments = [
            ("A_none", "none"),
            ("B_full", "full"),
            ("C_periodic", "periodic"),
            ("D_random_matched", "random_matched"),
            ("E_selective", "selective"),
            ("G_ecom", "ecom"),
            ("H_selective_deadline", "selective_deadline"),
            ("I_ecom_deadline", "ecom_deadline"),
        ]
        jobs = build_jobs(diag_paths, [0.0, 30.0, 120.0], diag_treatments, packet_loss_at_30=False)
        execute(jobs, "race_delay_diagnosis.csv", "race_delay_diagnosis_summary.json")

    if args.mode in {"expanded", "both"}:
        # Manageable primary matrix on full 60-scenario ensemble.
        # delay 0: full suite; delay 30/120: service–comm core + deadline refinement.
        jobs = []
        jobs += build_jobs(
            exp_paths,
            [0.0],
            [
                ("A_none", "none"),
                ("B_full", "full"),
                ("C_periodic", "periodic"),
                ("D_random_matched_bytes", "random_matched_bytes"),
                ("E_selective", "selective"),
                ("G_ecom", "ecom"),
                ("H_selective_deadline", "selective_deadline"),
                ("I_ecom_deadline", "ecom_deadline"),
            ],
        )
        jobs += build_jobs(
            exp_paths,
            [30.0, 120.0],
            [
                ("A_none", "none"),
                ("B_full", "full"),
                ("E_selective", "selective"),
                ("G_ecom", "ecom"),
                ("H_selective_deadline", "selective_deadline"),
                ("I_ecom_deadline", "ecom_deadline"),
            ],
        )
        execute(jobs, "race_expanded_dev.csv", "race_expanded_dev_summary.json")

    print("DONE", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
