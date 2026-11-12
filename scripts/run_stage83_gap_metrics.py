#!/usr/bin/env python
"""Stage 8.3 Task 5 fine metrics: claims, idle-with-pending, missed feasible, deferrals, imitation."""

from __future__ import annotations

import argparse
import json
import sys
from copy import deepcopy
from pathlib import Path

import pandas as pd
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def _factory(sc, graph, model, n_vehicles: int):
    reqs0 = deepcopy(sc.requests)

    def factory(seed=0, n_vehicles=n_vehicles):
        from race_casablanca.sim.types import RequestStatus

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

    return factory


def rollout_metrics(env, action_fn) -> dict:
    steps = env.reset(seed=0)
    n_charge = 0
    n_defer = 0
    n_claim_ops = 0
    while True:
        labels = action_fn(env, steps)
        for op, _comm in labels.values():
            if op == env.n_op - 1:  # OP_CHARGE
                n_charge += 1
            elif op == env.n_op - 2:  # OP_DEFER
                n_defer += 1
            else:
                n_claim_ops += 1
        steps = env.step(labels)
        if list(steps.values())[0].done:
            break
    m = env.final_metrics()
    m["n_charge_actions"] = n_charge
    m["n_defer_actions"] = n_defer
    m["n_claim_op_actions"] = n_claim_ops
    return m


def heldout_imitation(actor, teacher_fn, env, n_steps: int = 64) -> float:
    from race_casablanca.marl.env import OP_DEFER

    steps = env.reset(seed=123)
    match = 0
    tot = 0
    for _ in range(n_steps):
        labels = teacher_fn(env)
        for vid, st in steps.items():
            with torch.no_grad():
                o = torch.as_tensor(st.obs).unsqueeze(0)
                om = torch.as_tensor(st.op_mask).unsqueeze(0)
                cm = torch.as_tensor(st.comm_mask).unsqueeze(0)
                op_l, _ = actor(o, om, cm)
                pred = int(op_l.argmax(-1))
            match += int(pred == labels[vid][0])
            tot += 1
        # advance with teacher to stay on-policy for held-out labeling
        steps = env.step(labels)
        if list(steps.values())[0].done:
            steps = env.reset(seed=tot)
    return float(match / max(tot, 1))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n-vehicles", type=int, default=3)
    args = parser.parse_args()

    from race_casablanca.marl.bc import CooperativeTeacherAdapter, NativeBridgeTeacher
    from race_casablanca.marl.env import ABLATION_D, OP_CHARGE, OP_DEFER, RaceMultiAgentEnv
    from race_casablanca.marl.nets import FactorizedActor
    from race_casablanca.marl.scenarios import resolve_eval_dirs
    from race_casablanca.paths import project_root
    from race_casablanca.policies import ChargingController, GreedyInsertionPolicy, RaceCooperativePolicy
    from race_casablanca.sim.environment import OnlineSimulator, SimConfig
    from race_casablanca.sim.scenario_loader import load_congestion_model, load_drive_graph, load_scenario
    from race_casablanca.sim.types import RequestStatus

    root = project_root()
    out = root / "data" / "casablanca" / "online_results"
    ckpt_dir = out / "stage83_checkpoints"
    graph = load_drive_graph()
    model = load_congestion_model()
    paths = resolve_eval_dirs()

    rows = []

    def add_row(stage: str, path: Path, m: dict, **extra):
        rows.append(
            {
                "stage": stage,
                "scenario": path.name,
                "ot": m.get("on_time_rate_all"),
                "n_decisions": m.get("n_decisions"),
                "n_op_claims": m.get("n_op_claims", m.get("n_claims")),
                "n_claim_attempts": m.get("n_claim_attempts"),
                "n_op_defer": m.get("n_op_defer", m.get("n_defer_actions")),
                "n_op_charge": m.get("n_op_charge", m.get("n_charge_actions")),
                "n_idle_with_pending": m.get("n_idle_with_pending"),
                "n_missed_feasible_pickup": m.get("n_missed_feasible_pickup"),
                "n_duplicate_task_proposals": m.get("n_duplicate_task_proposals"),
                "n_second_choice_claims": m.get("n_second_choice_claims"),
                "n_bid_messages": m.get("n_bid_messages"),
                "n_bid_bytes": m.get("n_bid_bytes"),
                **extra,
            }
        )

    for path in paths:
        sc = load_scenario(path, load_network=False, graph=graph, model=model)
        print(f"gap-metrics {path.name}", flush=True)

        # A native
        reqs = deepcopy(sc.requests)
        for r in reqs:
            r.status = RequestStatus.UNRELEASED
            r.owner = None
        pol = RaceCooperativePolicy(comm_mode="selective", enable_readiness_charge=True, rng_seed=7)
        sim = OnlineSimulator(
            scenario_id=f"{sc.scenario_id}/gapA",
            graph=graph,
            model=model,
            requests=reqs,
            fleet={**sc.fleet, "n_vehicles": args.n_vehicles},
            depot_node=sc.depot_node,
            shift_start_s=sc.shift_start_s,
            shift_end_s=sc.shift_end_s,
            config=SimConfig(
                info_mode="restricted",
                seed=0,
                initial_soc=0.35,
                n_vehicles=args.n_vehicles,
                message_delay_s=0.0,
                day=str(getattr(sc, "day", "Monday")),
            ),
            policy=pol,
        )
        mA = sim.run().to_dict()
        mA["n_claims"] = pol.n_claims_success
        mA["n_bid_messages"] = getattr(sim, "n_bid_messages", 0)
        mA["n_bid_bytes"] = getattr(sim, "n_bid_bytes", 0)
        add_row("A_native", path, mA)

        # greedy charge70
        reqs = deepcopy(sc.requests)
        for r in reqs:
            r.status = RequestStatus.UNRELEASED
            r.owner = None
        gpol = GreedyInsertionPolicy(
            charging=ChargingController(mode="charge_to_target", target_soc=0.70)
        )
        gsim = OnlineSimulator(
            scenario_id=f"{sc.scenario_id}/greedy",
            graph=graph,
            model=model,
            requests=reqs,
            fleet={**sc.fleet, "n_vehicles": args.n_vehicles},
            depot_node=sc.depot_node,
            shift_start_s=sc.shift_start_s,
            shift_end_s=sc.shift_end_s,
            config=SimConfig(
                info_mode="full",
                seed=0,
                initial_soc=0.35,
                n_vehicles=args.n_vehicles,
                message_delay_s=0.0,
                day=str(getattr(sc, "day", "Monday")),
            ),
            policy=gpol,
        )
        mG = gsim.run().to_dict()
        add_row("G_greedy_charge70", path, mG)

        factory = _factory(sc, graph, model, args.n_vehicles)

        # B adapter
        env = RaceMultiAgentEnv(
            scenario_factory=factory,
            n_vehicles=args.n_vehicles,
            ablation=ABLATION_D,
            seed=0,
            max_decisions=2000,
            initial_soc=0.35,
        )
        adapter = CooperativeTeacherAdapter()

        def adapter_fn(e, steps):
            return adapter.actions(e)

        mB = rollout_metrics(env, adapter_fn)
        add_row("B_adapter", path, mB)

        # B2 intent bridge
        env = RaceMultiAgentEnv(
            scenario_factory=factory,
            n_vehicles=args.n_vehicles,
            ablation=ABLATION_D,
            seed=0,
            max_decisions=2000,
            initial_soc=0.35,
        )
        bridge = NativeBridgeTeacher(mode="intent")

        def intent_fn(e, steps):
            return bridge.actions(e)

        mI = rollout_metrics(env, intent_fn)
        add_row("B2_intent_bridge", path, mI)

        # C/D/E from checkpoints if present (seed 0)
        for stage, ckpt_name, abl in [
            ("C_bc_dagger", "stage83_bc_dagger_seed0.pt", ABLATION_D),
            ("E_mappo_A", "stage83_A_seed0.pt", "A_no_comm"),
            ("E_mappo_F", "stage83_F_race_marl_seed0.pt", "F_race_marl"),
            ("E_mappo_D", "stage83_D_selective_seed0.pt", ABLATION_D),
        ]:
            ckpt = ckpt_dir / ckpt_name
            if not ckpt.exists():
                continue
            env = RaceMultiAgentEnv(
                scenario_factory=factory,
                n_vehicles=args.n_vehicles,
                ablation=abl,
                seed=0,
                max_decisions=2000,
                initial_soc=0.35,
            )
            actor = FactorizedActor(env.obs_dim, env.n_op, env.n_comm)
            blob = torch.load(ckpt, map_location="cpu", weights_only=False)
            state = blob["actor"] if isinstance(blob, dict) and "actor" in blob else blob
            actor.load_state_dict(state)

            def actor_fn(e, steps, _actor=actor):
                actions = {}
                for vid, st in steps.items():
                    with torch.no_grad():
                        o = torch.as_tensor(st.obs).unsqueeze(0)
                        om = torch.as_tensor(st.op_mask).unsqueeze(0)
                        cm = torch.as_tensor(st.comm_mask).unsqueeze(0)
                        op_l, c_l = _actor(o, om, cm)
                        actions[vid] = (int(op_l.argmax(-1)), int(c_l.argmax(-1)))
                return actions

            m = rollout_metrics(env, actor_fn)
            # held-out imitation vs intent teacher on same scenario factory
            env_h = RaceMultiAgentEnv(
                scenario_factory=factory,
                n_vehicles=args.n_vehicles,
                ablation=ABLATION_D,
                seed=0,
                max_decisions=2000,
                initial_soc=0.35,
            )
            teacher = NativeBridgeTeacher(mode="intent")
            im_acc = heldout_imitation(actor, teacher.actions, env_h, n_steps=48)
            add_row(stage, path, m, heldout_op_imitation=im_acc)

    df = pd.DataFrame(rows)
    df.to_csv(out / "stage83_gap_metrics.csv", index=False)
    summary = (
        df.groupby("stage")[
            [
                "ot",
                "n_op_claims",
                "n_claim_attempts",
                "n_op_defer",
                "n_op_charge",
                "n_idle_with_pending",
                "n_missed_feasible_pickup",
                "n_duplicate_task_proposals",
                "heldout_op_imitation",
            ]
        ]
        .mean(numeric_only=True)
        .reset_index()
    )
    summary.to_csv(out / "stage83_gap_metrics_summary.csv", index=False)
    (out / "stage83_gap_metrics_summary.json").write_text(
        summary.to_json(orient="records", indent=2), encoding="utf-8"
    )
    print(summary.to_string(index=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
