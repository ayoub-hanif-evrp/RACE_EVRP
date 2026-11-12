#!/usr/bin/env python
"""Run native RaceCooperativePolicy logic at corrected MARL decision epochs.

No factorized action adapter: each MARL decision point calls policy.on_decision
with RestrictedObservation + ActionInterface, then flushes autoleg.

If OT ≈ native standalone (~0.83), event parity is sufficient and the adapter
is the remaining bottleneck. If OT ≈ adapter (~0.63), residual schedule/API gaps remain.
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


def run_bridge(sc, graph, model, *, n_vehicles: int, delay: float, mode: str):
    from race_casablanca.marl.env import ABLATION_A, ABLATION_B, ABLATION_D, RaceMultiAgentEnv
    from race_casablanca.policies import RaceCooperativePolicy
    from race_casablanca.sim.policy_api import ActionInterface, build_restricted_observation
    from race_casablanca.sim.types import RequestStatus

    abl = {"none": ABLATION_A, "full": ABLATION_B, "selective": ABLATION_D}[mode]
    reqs0 = deepcopy(sc.requests)

    def factory(seed: int = 0, n_vehicles: int = n_vehicles):
        reqs = deepcopy(reqs0)
        for r in reqs:
            r.status = RequestStatus.UNRELEASED
            r.owner = None
        return {
            "scenario_id": f"{sc.scenario_id}/bridge",
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
        initial_soc=0.35,
        message_delay_s=delay,
        ablation=abl,
        seed=0,
        max_decisions=2000,
    )
    pol = RaceCooperativePolicy(comm_mode=mode, enable_readiness_charge=True, rng_seed=7)
    steps = env.reset(seed=0)
    while True:
        reason = env._last_decision_reason or "epoch"
        # Native per-vehicle decisions at this synchronized epoch
        for vid in list(env._agent_ids):
            obs = build_restricted_observation(env.sim, vid)
            act = ActionInterface(env.sim, actor_vehicle_id=vid)
            pol.on_decision(obs, act, reason)
        env._flush_autoleg()
        # Advance without consuming a dummy neural action: reuse empty defer step
        # by calling advance directly after marking a synthetic decision count.
        env._n_decisions += 1
        done = env._advance_to_decision()
        if env._n_decisions >= env.max_decisions:
            done = True
        if done:
            while env.sim._eq:
                env._flush_autoleg()
                if env._advance_to_decision():
                    break
            env._flush_autoleg()
            break
        # Refresh observations for next loop
        env._observe_all(reward=0.0, done=False)
    m = env.sim._metrics().to_dict()
    return {
        "method": f"bridge_{mode}",
        "on_time_rate_all": float(m["on_time_rate_all"]),
        "n_served": float(m["n_served"]),
        "n_decisions": float(env._n_decisions),
        "n_decision_service_end": float(env._n_decision_service_end),
        "policy_msgs": float(pol.n_messages_sent_by_policy),
        "n_claims_success": float(pol.n_claims_success),
    }


def main() -> int:
    from race_casablanca.marl.scenarios import resolve_eval_dirs
    from race_casablanca.paths import project_root
    from race_casablanca.sim.scenario_loader import load_congestion_model, load_drive_graph, load_scenario

    root = project_root()
    out = root / "data" / "casablanca" / "online_results"
    graph = load_drive_graph()
    model = load_congestion_model()
    rows = []
    for path in resolve_eval_dirs():
        sc = load_scenario(path, load_network=False, graph=graph, model=model)
        for mode in ("selective", "none"):
            print(f"bridge {path.name} {mode}", flush=True)
            r = run_bridge(sc, graph, model, n_vehicles=3, delay=0.0, mode=mode)
            r["scenario"] = path.name
            rows.append(r)
    df = pd.DataFrame(rows)
    df.to_csv(out / "stage83_native_bridge.csv", index=False)
    summary = df.groupby("method")["on_time_rate_all"].mean().to_dict()
    (out / "stage83_native_bridge_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
