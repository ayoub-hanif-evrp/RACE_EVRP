#!/usr/bin/env python
"""Final development gate: corrected timing causality + 60-scenario closeout.

Preserves historical PASS1 / prior-devval artifacts. Does NOT touch locked_final.
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


TREATMENTS_D0 = [
    ("A_none", "none", {}),
    ("B_full", "full", {}),
    ("C_periodic", "periodic", {}),
    ("D_random_matched_bytes", "random_matched_bytes", {}),
    ("E_event_triggered", "event_triggered", {}),
    ("F_selective", "selective", {}),
    ("G_ecom", "ecom", {}),
    ("H_selective_deadline", "selective", {"assign_wait_mode": "deadline_energy", "delay_aware_trust": True, "max_assign_wait_s": 60.0}),
    ("I_central_greedy", "central_greedy", {}),
]

TREATMENTS_DELAY = [
    ("A_none", "none", {}),
    ("B_full", "full", {}),
    ("E_event_triggered", "event_triggered", {}),
    ("F_selective", "selective", {}),
    ("G_ecom", "ecom", {}),
    ("H_selective_deadline", "selective", {"assign_wait_mode": "deadline_energy", "delay_aware_trust": True, "max_assign_wait_s": 60.0}),
]


def default_dev_dirs() -> list[Path]:
    from race_casablanca.paths import project_root

    base = project_root() / "data" / "casablanca" / "evaluation_v1" / "default"
    return sorted([p for p in base.iterdir() if p.is_dir()])


def make_policy(mode: str, *, matched_msgs: int, matched_bytes: float, n_vehicles: int, delay: float, extra: dict):
    from race_casablanca.policies.greedy import GreedyInsertionPolicy
    from race_casablanca.policies.race_cert_hybrid import make_hybrid
    from race_casablanca.policies.race_cooperative import RaceCooperativePolicy

    if mode == "central_greedy":
        # Full-info external reference (more information than restricted treatments).
        return GreedyInsertionPolicy()

    kw = dict(
        rng_seed=7,
        enable_readiness_charge=True,
        matched_n_recipients=max(1, n_vehicles - 1),
        message_delay_s=float(delay),
        fair_physical_decisions=True,
        **extra,
    )
    if mode == "random_matched_bytes":
        return RaceCooperativePolicy(
            comm_mode="random_matched_bytes",
            matched_byte_budget=float(matched_bytes),
            typical_payload_bytes=max(200.0, matched_bytes / max(1, matched_msgs)),
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
    extra = dict(payload.get("extra") or {})
    event_trace = bool(payload.get("event_trace", False))

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
        extra=extra,
    )
    if hasattr(policy, "_matched_bytes") and getattr(policy, "_matched_bytes", None) is not None:
        policy._matched_bytes.n_recipients = max(1, n_vehicles - 1)

    info_mode = "full" if mode == "central_greedy" else "restricted"
    cfg = SimConfig(
        info_mode=info_mode,
        seed=0,
        initial_soc=soc,
        n_vehicles=n_vehicles,
        message_delay_s=0.0 if mode == "central_greedy" else delay,
        packet_loss_p=0.0,
        packet_loss_seed=0,
        periodic_broadcast_s=300.0 if mode == "periodic" else 0.0,
        periodic_state_broadcast=False,
        message_triggers_decision=True,
        decision_on_release=True,
        day=str(getattr(sc, "day", "Monday")),
    )
    if event_trace:
        cfg.record_event_trace = True  # type: ignore[attr-defined]

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
    # Release-to-commit latency via request owner timestamps if available
    release_s = {r.request_id: float(r.release_s) for r in reqs}
    m = sim.run().to_dict()
    wall = time.time() - t0

    commit_latencies = []
    for rid, req in sim.requests.items():
        if req.owner and req.service_start_s is not None:
            commit_latencies.append(float(req.service_start_s) - float(release_s.get(rid, req.release_s)))
        elif req.owner:
            # Approximate with first ownership — registry has no claim time; use 0 marker
            pass

    owners = {rid: req.owner for rid, req in sim.requests.items() if req.owner}
    return {
        "scenario": path.name,
        "treatment": label,
        "comm_mode": mode,
        "delay_s": delay,
        "on_time_rate_all": float(m.get("on_time_rate_all", 0.0)),
        "n_on_time": float(m.get("n_on_time", 0.0)),
        "n_served": float(m.get("n_served", 0.0)),
        "n_requests": float(m.get("n_requests", 0.0)),
        "n_missed": float(m.get("n_missed", 0.0)),
        "n_expired": float(m.get("n_expired", 0.0)),
        "n_bid_messages": float(getattr(sim, "n_bid_messages", 0) or 0),
        "n_bid_bytes": float(getattr(sim, "n_bid_bytes", 0) or 0),
        "mean_assign_wait_s": (
            float(sim.sum_assign_wait_s) / float(sim.n_assign_windows)
            if getattr(sim, "n_assign_windows", 0)
            else 0.0
        ),
        "sum_assign_wait_s": float(getattr(sim, "sum_assign_wait_s", 0.0) or 0.0),
        "n_assign_deferred": float(getattr(sim, "n_assign_deferred", 0) or 0),
        "n_assign_immediate": float(getattr(sim, "n_assign_immediate", 0) or 0),
        "n_defers_to_peer": float(getattr(policy, "n_defers_to_peer", 0) or 0),
        "n_info_only_decisions": float(getattr(policy, "n_info_only_decisions", 0) or 0),
        "n_physical_claim_decisions": float(getattr(policy, "n_physical_claim_decisions", 0) or 0),
        "n_claims_ignored_stale_peer": float(getattr(policy, "n_claims_ignored_stale_peer", 0) or 0),
        "n_counterfactual_decision_changes": float(getattr(policy, "n_counterfactual_decision_changes", 0) or 0),
        "n_ecom_proved": float(getattr(policy, "n_ecom_proved", 0) or 0),
        "n_ecom_fallback": float(getattr(policy, "n_ecom_fallback", 0) or 0),
        "n_ecom_heuristic": float(getattr(policy, "n_ecom_heuristic", 0) or 0),
        "battery_reserve_violations": float(m.get("battery_reserve_violations", 0) or 0),
        "battery_exhaustion": float(m.get("battery_exhaustion", 0) or 0),
        "n_charges": float(m.get("n_charges", 0) or 0),
        "energy_consumed_kwh": float(m.get("energy_consumed_kwh", 0) or 0),
        "mean_decision_runtime_s": float(m.get("mean_decision_runtime_s", 0) or 0),
        "mean_release_to_service_s": float(np.mean(commit_latencies)) if commit_latencies else float("nan"),
        "wall_s": wall,
        "owners_json": json.dumps(owners, sort_keys=True),
    }


def calibrate(paths: list[Path], *, n_vehicles: int, soc: float) -> tuple[int, float]:
    rows = []
    for p in paths:
        rows.append(
            run_one(
                {
                    "path": str(p),
                    "mode": "selective",
                    "label": "F_selective",
                    "delay": 0.0,
                    "n_vehicles": n_vehicles,
                    "soc": soc,
                    "matched_msgs": 10**9,
                    "matched_bytes": 1e18,
                    "extra": {},
                }
            )
        )
    msgs = max(1, int(round(float(np.mean([r["n_bid_messages"] for r in rows])))))
    nbytes = float(np.mean([r["n_bid_bytes"] for r in rows]))
    return msgs, nbytes


def summarize(df: pd.DataFrame, noninf: dict) -> dict:
    out = {"noninferiority_margin": noninf, "by_delay": {}}
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
                    "n_info_only_decisions",
                    "n_physical_claim_decisions",
                    "n_ecom_proved",
                    "battery_reserve_violations",
                    "wall_s",
                ]
            ]
            .mean()
            .reset_index()
            .to_dict(orient="records")
        )
        paired = {}
        if (g.treatment == "F_selective").any():
            sel = g[g.treatment == "F_selective"].set_index("scenario")
            for t, tg in g.groupby("treatment"):
                o = tg.set_index("scenario")
                d = (o["on_time_rate_all"] - sel["on_time_rate_all"]).dropna()
                if len(d) == 0:
                    continue
                sem = float(d.sem()) if len(d) > 1 else 0.0
                paired[t] = {
                    "n": int(len(d)),
                    "mean_dOT": float(d.mean()),
                    "ci95": [float(d.mean() - 1.96 * sem), float(d.mean() + 1.96 * sem)],
                    "wins": int((d > 1e-12).sum()),
                    "ties": int((d.abs() <= 1e-12).sum()),
                    "losses": int((d < -1e-12).sum()),
                    "mean_byte_ratio_vs_sel": float(
                        (o["n_bid_bytes"] / sel["n_bid_bytes"].replace(0, np.nan)).mean()
                    ),
                }
        out["by_delay"][str(delay)] = {"means": means, "paired_vs_selective": paired}
    return out


def run_event_traces(out: Path, matched_msgs: int, matched_bytes: float) -> None:
    """Compact timing audit on one development scenario for all primary treatments."""
    from race_casablanca.marl.scenarios import resolve_eval_dirs

    paths = resolve_eval_dirs()
    if not paths:
        return
    path = paths[0]
    rows = []
    for label, mode, extra in [
        ("A_none", "none", {}),
        ("B_full", "full", {}),
        ("C_periodic", "periodic", {}),
        ("E_event_triggered", "event_triggered", {}),
        ("F_selective", "selective", {}),
        ("G_ecom", "ecom", {}),
        ("H_selective_deadline", "selective", {"assign_wait_mode": "deadline_energy", "delay_aware_trust": True}),
    ]:
        for delay in (0.0, 30.0, 120.0):
            row = run_one(
                {
                    "path": str(path),
                    "mode": mode,
                    "label": label,
                    "delay": delay,
                    "n_vehicles": 3,
                    "soc": 0.35,
                    "matched_msgs": matched_msgs,
                    "matched_bytes": matched_bytes,
                    "extra": extra,
                }
            )
            rows.append(row)
            print(
                f"TRACE {path.name} d={delay} {label} OT={row['on_time_rate_all']:.3f} "
                f"wait={row['mean_assign_wait_s']:.1f} deferred={row['n_assign_deferred']:.0f} "
                f"info_only={row['n_info_only_decisions']:.0f} phys={row['n_physical_claim_decisions']:.0f}",
                flush=True,
            )
    pd.DataFrame(rows).to_csv(out / "race_closeout_event_timing_trace.csv", index=False)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--limit-scenarios", type=int, default=0)
    parser.add_argument("--skip-expanded", action="store_true")
    args = parser.parse_args()

    from race_casablanca.paths import scenarios_dir

    out = ROOT / "data" / "casablanca" / "online_results"
    out.mkdir(parents=True, exist_ok=True)

    noninf = {
        "primary_metric": "on_time_rate_all",
        "comparator": "F_selective",
        "margin_absolute_ot": 0.02,
        "rationale": "2pp OT ≈ 0.64 requests / 32-request episode; frozen before closeout inspection.",
        "frozen_before_expanded_eval": True,
    }
    (out / "race_closeout_noninferiority_margin.json").write_text(json.dumps(noninf, indent=2), encoding="utf-8")

    train_paths = [p for p in sorted((scenarios_dir() / "train").iterdir()) if p.is_dir()][:8]
    print(f"Calibrating on {len(train_paths)} train scenarios...", flush=True)
    matched_msgs, matched_bytes = calibrate(train_paths, n_vehicles=3, soc=0.35)
    print(f"matched_msgs={matched_msgs} matched_bytes={matched_bytes:.1f}", flush=True)
    (out / "race_closeout_matched_budget.json").write_text(
        json.dumps({"matched_recipient_messages": matched_msgs, "matched_bytes": matched_bytes}, indent=2),
        encoding="utf-8",
    )

    print("Running event-timing traces...", flush=True)
    run_event_traces(out, matched_msgs, matched_bytes)

    if args.skip_expanded:
        return 0

    exp_paths = default_dev_dirs()
    if args.limit_scenarios > 0:
        exp_paths = exp_paths[: args.limit_scenarios]

    jobs = []
    for p in exp_paths:
        for label, mode, extra in TREATMENTS_D0:
            jobs.append(
                {
                    "path": str(p),
                    "mode": mode,
                    "label": label,
                    "delay": 0.0,
                    "n_vehicles": 3,
                    "soc": 0.35,
                    "matched_msgs": matched_msgs,
                    "matched_bytes": matched_bytes,
                    "extra": extra,
                }
            )
        for delay in (30.0, 120.0):
            for label, mode, extra in TREATMENTS_DELAY:
                jobs.append(
                    {
                        "path": str(p),
                        "mode": mode,
                        "label": label,
                        "delay": delay,
                        "n_vehicles": 3,
                        "soc": 0.35,
                        "matched_msgs": matched_msgs,
                        "matched_bytes": matched_bytes,
                        "extra": extra,
                    }
                )

    csv_path = out / "race_closeout_expanded_dev.csv"
    rows = []
    print(f"Running {len(jobs)} closeout jobs with {args.workers} workers...", flush=True)
    with ProcessPoolExecutor(max_workers=max(1, args.workers)) as ex:
        futs = {ex.submit(run_one, j): j for j in jobs}
        done = 0
        for fut in as_completed(futs):
            row = fut.result()
            rows.append(row)
            done += 1
            if done % 20 == 0 or done == len(jobs):
                print(f"  progress {done}/{len(jobs)} last={row['scenario']}/{row['treatment']}/d{row['delay_s']}", flush=True)
                pd.DataFrame(rows).to_csv(csv_path, index=False)
    df = pd.DataFrame(rows)
    df.to_csv(csv_path, index=False)
    summary = summarize(df, noninf)
    (out / "race_closeout_expanded_dev_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print("DONE", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
