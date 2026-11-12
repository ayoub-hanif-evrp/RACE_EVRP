#!/usr/bin/env python
"""Stage 8.3 Task 2 deep: native vs MARL-adapter vs intent-bridge first-divergence traces.

Conditions: peak / tight / baseline (normal) / SOC=0.35 / delay=0 and delay=30.
Records request-level ownership + first action divergence explanations.
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


def _owners(sim) -> dict[str, str | None]:
    return {rid: req.owner for rid, req in sim.requests.items()}


def run_native(sc, graph, model, *, n_vehicles: int, soc: float, delay: float):
    from race_casablanca.policies import RaceCooperativePolicy
    from race_casablanca.sim.environment import OnlineSimulator, SimConfig
    from race_casablanca.sim.types import RequestStatus

    reqs = deepcopy(sc.requests)
    for r in reqs:
        r.status = RequestStatus.UNRELEASED
        r.owner = None
    pol = RaceCooperativePolicy(comm_mode="selective", enable_readiness_charge=True, rng_seed=7)
    sim = OnlineSimulator(
        scenario_id=f"{sc.scenario_id}/native_div",
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
            message_delay_s=delay,
            packet_loss_p=0.0,
            periodic_state_broadcast=False,
            decision_on_release=True,
            day=str(getattr(sc, "day", "Monday")),
        ),
        policy=pol,
    )
    m = sim.run().to_dict()
    return {
        "ot": float(m["on_time_rate_all"]),
        "n_decisions": float(m.get("n_decisions", 0)),
        "n_claims": float(pol.n_claims_success),
        "n_msgs": float(getattr(sim, "n_bid_messages", 0) or 0),
        "owners": _owners(sim),
        "completed": {
            rid: bool(req.status.name == "COMPLETED" and req.on_time)
            for rid, req in sim.requests.items()
        },
    }


def run_marl_teacher(sc, graph, model, *, n_vehicles: int, soc: float, delay: float, teacher: str):
    from race_casablanca.marl.bc import CooperativeTeacherAdapter, NativeBridgeTeacher
    from race_casablanca.marl.env import ABLATION_D, RaceMultiAgentEnv
    from race_casablanca.sim.types import RequestStatus

    reqs0 = deepcopy(sc.requests)

    def factory(seed=0, n_vehicles=n_vehicles):
        reqs = deepcopy(reqs0)
        for r in reqs:
            r.status = RequestStatus.UNRELEASED
            r.owner = None
        return {
            "scenario_id": sc.scenario_id,
            "graph": graph,
            "model": model,
            "requests": reqs,
            "fleet": {**sc.fleet, "n_vehicles": n_vehicles},
            "depot_node": sc.depot_node,
            "shift_start_s": sc.shift_start_s,
            "shift_end_s": sc.shift_end_s,
            "day": getattr(sc, "day", "Monday"),
        }

    env = RaceMultiAgentEnv(
        scenario_factory=factory,
        n_vehicles=n_vehicles,
        ablation=ABLATION_D,
        seed=0,
        max_decisions=2000,
        initial_soc=soc,
        message_delay_s=delay,
    )
    if teacher == "adapter":
        teach = CooperativeTeacherAdapter()
    else:
        teach = NativeBridgeTeacher(mode="intent")
    steps = env.reset(seed=0)
    teach.reset()
    epochs = []
    while True:
        reason = getattr(env, "_last_decision_reason", "")
        now = float(env.sim.now_s) if env.sim else -1.0
        avail = sorted(
            r.request_id
            for r in env.sim.requests.values()
            if r.status == RequestStatus.AVAILABLE and r.owner is None
        )
        idle = [
            vid
            for vid, v in env.sim.vehicles.items()
            if (not v.busy) and str(v.mode.value) == "idle"
        ]
        labels = teach.actions(env)
        epochs.append(
            {
                "t": now,
                "reason": reason,
                "available": avail,
                "idle": idle,
                "actions": {vid: {"op": int(a[0]), "comm": int(a[1])} for vid, a in labels.items()},
                "owners_before": _owners(env.sim),
            }
        )
        steps = env.step(labels)
        epochs[-1]["owners_after"] = _owners(env.sim)
        if list(steps.values())[0].done:
            break
    m = env.final_metrics()
    return {
        "ot": float(m.get("on_time_rate_all", 0.0)),
        "n_decisions": float(m.get("n_decisions", 0)),
        "n_claims": float(m.get("n_op_claims", 0)),
        "n_msgs": float(m.get("n_bid_messages", 0)),
        "n_idle_with_pending": float(m.get("n_idle_with_pending", 0)),
        "n_missed_feasible_pickup": float(m.get("n_missed_feasible_pickup", 0)),
        "owners": _owners(env.sim) if env.sim else {},
        "completed": {
            rid: bool(req.status.name == "COMPLETED" and req.on_time)
            for rid, req in (env.sim.requests.items() if env.sim else [])
        },
        "epochs": epochs,
    }


def first_owner_divergence(native_owners: dict, other_owners: dict) -> dict | None:
    keys = sorted(set(native_owners) | set(other_owners))
    for k in keys:
        if native_owners.get(k) != other_owners.get(k):
            return {
                "request_id": k,
                "native_owner": native_owners.get(k),
                "other_owner": other_owners.get(k),
            }
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n-vehicles", type=int, default=3)
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

    # Map conditions: normal=baseline, peak, tight; always SOC 0.35; delays 0 and 30
    conditions = []
    for path in paths:
        name = path.name
        if "baseline" in name:
            kind = "normal_workload"
        elif "peak" in name:
            kind = "peak_workload"
        elif "tight" in name:
            kind = "tight_windows"
        else:
            kind = "other"
        for delay in (0.0, 30.0):
            conditions.append((kind, path, 0.35, delay))

    rows = []
    divergences = []
    for kind, path, soc, delay in conditions:
        sc = load_scenario(path, load_network=False, graph=graph, model=model)
        print(f"divergence {kind} {path.name} soc={soc} delay={delay}", flush=True)
        native = run_native(sc, graph, model, n_vehicles=args.n_vehicles, soc=soc, delay=delay)
        adapter = run_marl_teacher(
            sc, graph, model, n_vehicles=args.n_vehicles, soc=soc, delay=delay, teacher="adapter"
        )
        intent = run_marl_teacher(
            sc, graph, model, n_vehicles=args.n_vehicles, soc=soc, delay=delay, teacher="intent"
        )
        for label, other in [("adapter", adapter), ("intent", intent)]:
            div = first_owner_divergence(native["owners"], other["owners"])
            completed_diff = sorted(
                rid
                for rid in set(native["completed"]) | set(other["completed"])
                if native["completed"].get(rid) != other["completed"].get(rid)
            )
            # First epoch where owner set differs from native final for early signal
            first_epoch_note = None
            if other.get("epochs"):
                for i, ep in enumerate(other["epochs"]):
                    # Compare cumulative owners after epoch against native final for claimed ids
                    after = ep.get("owners_after") or {}
                    for rid, own in after.items():
                        if own and native["owners"].get(rid) and own != native["owners"].get(rid):
                            first_epoch_note = {
                                "epoch_i": i,
                                "t": ep["t"],
                                "reason": ep["reason"],
                                "request_id": rid,
                                "marl_owner": own,
                                "native_final_owner": native["owners"].get(rid),
                                "available": ep.get("available"),
                                "actions": ep.get("actions"),
                            }
                            break
                    if first_epoch_note:
                        break
            expl = {
                "scenario": path.name,
                "condition": kind,
                "soc": soc,
                "delay_s": delay,
                "compare": label,
                "native_ot": native["ot"],
                "other_ot": other["ot"],
                "ot_gap": native["ot"] - other["ot"],
                "first_owner_divergence": div,
                "n_completed_on_time_diffs": len(completed_diff),
                "completed_on_time_diff_ids": completed_diff[:12],
                "first_conflicting_claim_epoch": first_epoch_note,
                "other_idle_with_pending": other.get("n_idle_with_pending"),
                "other_missed_feasible": other.get("n_missed_feasible_pickup"),
                "request_level_explanation": (
                    f"First ownership mismatch on {div['request_id']}: "
                    f"native={div['native_owner']} vs {label}={div['other_owner']}"
                    if div
                    else "No ownership mismatch; OT gap (if any) from timing/completion, not final owner set."
                ),
            }
            divergences.append(expl)
            rows.append(
                {
                    "scenario": path.name,
                    "condition": kind,
                    "soc": soc,
                    "delay_s": delay,
                    "method": "native",
                    "ot": native["ot"],
                    "n_decisions": native["n_decisions"],
                    "n_claims": native["n_claims"],
                    "n_msgs": native["n_msgs"],
                }
            )
            rows.append(
                {
                    "scenario": path.name,
                    "condition": kind,
                    "soc": soc,
                    "delay_s": delay,
                    "method": label,
                    "ot": other["ot"],
                    "n_decisions": other["n_decisions"],
                    "n_claims": other["n_claims"],
                    "n_msgs": other["n_msgs"],
                    "n_idle_with_pending": other.get("n_idle_with_pending"),
                    "n_missed_feasible_pickup": other.get("n_missed_feasible_pickup"),
                }
            )

    pd.DataFrame(rows).to_csv(out / "stage83_teacher_divergence_metrics.csv", index=False)
    (out / "stage83_teacher_divergence_traces.json").write_text(
        json.dumps(divergences, indent=2, default=str), encoding="utf-8"
    )
    summary = {
        "n_comparisons": len(divergences),
        "mean_ot_gap_adapter": float(
            pd.DataFrame([d for d in divergences if d["compare"] == "adapter"])["ot_gap"].mean()
        ),
        "mean_ot_gap_intent": float(
            pd.DataFrame([d for d in divergences if d["compare"] == "intent"])["ot_gap"].mean()
        ),
        "n_with_owner_divergence_adapter": sum(
            1 for d in divergences if d["compare"] == "adapter" and d["first_owner_divergence"]
        ),
        "n_with_owner_divergence_intent": sum(
            1 for d in divergences if d["compare"] == "intent" and d["first_owner_divergence"]
        ),
    }
    (out / "stage83_teacher_divergence_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
