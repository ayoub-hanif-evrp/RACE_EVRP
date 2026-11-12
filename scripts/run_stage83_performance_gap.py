#!/usr/bin/env python
"""Stage 8.3 Task 5: decompose OT gap across native → adapter → BC → DAgger → MAPPO."""

from __future__ import annotations

import argparse
import json
import sys
from copy import deepcopy
from pathlib import Path

import numpy as np
import pandas as pd
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def _factory_from_scenario(sc, graph, model, n_vehicles: int):
    reqs0 = deepcopy(sc.requests)

    def factory(seed: int = 0, n_vehicles: int = n_vehicles):
        from race_casablanca.sim.types import RequestStatus

        reqs = deepcopy(reqs0)
        for r in reqs:
            r.status = RequestStatus.UNRELEASED
            r.owner = None
        return {
            "scenario_id": f"{sc.scenario_id}/gap",
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


def eval_actor(env, actor, device="cpu") -> dict:
    from race_casablanca.marl.env import COMM_SUPPRESS

    steps = env.reset(seed=0)
    actor.eval()
    while True:
        actions = {}
        for vid, st in steps.items():
            with torch.no_grad():
                o = torch.as_tensor(st.obs, device=device).unsqueeze(0)
                om = torch.as_tensor(st.op_mask, device=device).unsqueeze(0)
                cm = torch.as_tensor(st.comm_mask, device=device).unsqueeze(0)
                op_l, comm_l = actor(o, om, cm)
                actions[vid] = (int(op_l.argmax(-1)), int(comm_l.argmax(-1)))
        steps = env.step(actions)
        if list(steps.values())[0].done:
            break
    return env.final_metrics()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n-vehicles", type=int, default=3)
    parser.add_argument("--bc-steps", type=int, default=384)
    parser.add_argument("--bc-epochs", type=int, default=40)
    parser.add_argument("--dagger-rounds", type=int, default=2)
    parser.add_argument("--mappo-iters", type=int, default=15)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    from race_casablanca.marl.bc import (
        CooperativeTeacherAdapter,
        behavior_clone,
        collect_bc_batch,
        cooperative_teacher_actions,
        dagger_aggregate,
        evaluate_bc_accuracy,
    )
    from race_casablanca.marl.env import ABLATION_A, ABLATION_D, RaceMultiAgentEnv
    from race_casablanca.marl.mappo import MAPPOTrainer
    from race_casablanca.marl.nets import FactorizedActor
    from race_casablanca.marl.scenarios import resolve_eval_dirs
    from race_casablanca.paths import project_root
    from race_casablanca.policies import RaceCooperativePolicy
    from race_casablanca.sim.environment import OnlineSimulator, SimConfig
    from race_casablanca.sim.scenario_loader import load_congestion_model, load_drive_graph, load_scenario
    from race_casablanca.sim.types import RequestStatus

    root = project_root()
    out_dir = root / "data" / "casablanca" / "online_results"
    graph = load_drive_graph()
    model = load_congestion_model()
    paths = resolve_eval_dirs()

    # Train BC/DAgger/MAPPO once on train pool, evaluate gap on each val scenario
    from race_casablanca.marl.scenarios import load_casablanca_pool, make_pool_factory

    pool = load_casablanca_pool(split="train")
    train_factory = make_pool_factory(pool, n_vehicles=args.n_vehicles, procedural_jitter=True)
    train_env = RaceMultiAgentEnv(
        scenario_factory=train_factory,
        n_vehicles=args.n_vehicles,
        ablation=ABLATION_D,
        seed=args.seed,
        max_decisions=400,
    )
    device = "cpu"
    actor = FactorizedActor(train_env.obs_dim, train_env.n_op, train_env.n_comm)
    print("BC...", flush=True)
    batch = collect_bc_batch(
        train_env, n_steps=args.bc_steps, seed=args.seed + 50, teacher="cooperative"
    )
    behavior_clone(actor, batch, epochs=args.bc_epochs, device=device)
    bc_acc = evaluate_bc_accuracy(actor, batch, device=device)
    actor_bc = FactorizedActor(train_env.obs_dim, train_env.n_op, train_env.n_comm)
    actor_bc.load_state_dict(actor.state_dict())

    print("DAgger...", flush=True)
    for r in range(args.dagger_rounds):
        batch = dagger_aggregate(
            train_env, actor, n_steps=args.bc_steps // 2, seed=args.seed + 200 + r, device=device, prior_batch=batch
        )
        behavior_clone(actor, batch, epochs=max(10, args.bc_epochs // 2), device=device)
    dag_acc = evaluate_bc_accuracy(actor, batch, device=device)
    actor_dag = FactorizedActor(train_env.obs_dim, train_env.n_op, train_env.n_comm)
    actor_dag.load_state_dict(actor.state_dict())

    print("MAPPO freeze_comm A...", flush=True)
    env_a = RaceMultiAgentEnv(
        scenario_factory=train_factory,
        n_vehicles=args.n_vehicles,
        ablation=ABLATION_A,
        seed=args.seed,
        max_decisions=400,
    )
    trainer = MAPPOTrainer(env_a, freeze_comm=True)
    trainer.actor.load_state_dict(actor.state_dict())
    # Validation-based selection on first eval scenario
    val_sc = load_scenario(paths[0], load_network=False, graph=graph, model=model)
    val_factory = _factory_from_scenario(val_sc, graph, model, args.n_vehicles)
    best_ot, best_state = -1.0, None
    for i in range(args.mappo_iters):
        buf, boot, _ = trainer.collect(48)
        trainer.update(buf, last_value=boot)
        if (i + 1) % 5 == 0:
            ve = RaceMultiAgentEnv(
                scenario_factory=val_factory,
                n_vehicles=args.n_vehicles,
                ablation=ABLATION_A,
                seed=0,
                max_decisions=2000,
            )
            m = eval_actor(ve, trainer.actor)
            ot = float(m.get("on_time_rate_all", 0.0))
            print(f"  val iter={i+1} ot={ot:.3f}", flush=True)
            if ot >= best_ot:
                best_ot = ot
                best_state = {k: v.detach().cpu().clone() for k, v in trainer.actor.state_dict().items()}
    if best_state is not None:
        trainer.actor.load_state_dict(best_state)
    actor_mappo = trainer.actor

    rows = []
    for path in paths:
        sc = load_scenario(path, load_network=False, graph=graph, model=model)
        # A native
        reqs = deepcopy(sc.requests)
        for r in reqs:
            r.status = RequestStatus.UNRELEASED
            r.owner = None
        pol = RaceCooperativePolicy(comm_mode="selective", enable_readiness_charge=True, rng_seed=7)
        sim = OnlineSimulator(
            scenario_id=sc.scenario_id,
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
                periodic_state_broadcast=False,
                day=str(getattr(sc, "day", "Monday")),
            ),
            policy=pol,
        )
        nm = sim.run().to_dict()
        rows.append({"scenario": path.name, "stage": "A_native", "ot": nm["on_time_rate_all"], "n_decisions": nm.get("n_decisions")})

        factory = _factory_from_scenario(sc, graph, model, args.n_vehicles)
        # B adapter
        env = RaceMultiAgentEnv(scenario_factory=factory, n_vehicles=args.n_vehicles, ablation=ABLATION_D, seed=0, max_decisions=2000)
        adapter = CooperativeTeacherAdapter()
        steps = env.reset(seed=0)
        adapter.reset()
        while True:
            steps = env.step(cooperative_teacher_actions(env, adapter))
            if list(steps.values())[0].done:
                break
        bm = env.final_metrics()
        rows.append({"scenario": path.name, "stage": "B_adapter", "ot": bm["on_time_rate_all"], "n_decisions": bm["n_decisions"], "n_service_end": bm.get("n_decision_service_end")})

        for label, act in [("C_bc", actor_bc), ("D_dagger", actor_dag), ("E_mappo", actor_mappo)]:
            env = RaceMultiAgentEnv(scenario_factory=factory, n_vehicles=args.n_vehicles, ablation=ABLATION_A if label == "E_mappo" else ABLATION_D, seed=0, max_decisions=2000)
            mm = eval_actor(env, act)
            rows.append({"scenario": path.name, "stage": label, "ot": mm.get("on_time_rate_all"), "n_decisions": mm.get("n_decisions"), "n_claims": mm.get("n_op_claims")})

    df = pd.DataFrame(rows)
    df.to_csv(out_dir / "stage83_performance_gap.csv", index=False)
    means = df.groupby("stage")["ot"].mean().to_dict()
    summary = {
        "means": means,
        "bc_acc": bc_acc,
        "dagger_acc": dag_acc,
        "gap_native_adapter": float(means.get("A_native", 0) - means.get("B_adapter", 0)),
        "gap_adapter_bc": float(means.get("B_adapter", 0) - means.get("C_bc", 0)),
        "gap_bc_dagger": float(means.get("C_bc", 0) - means.get("D_dagger", 0)),
        "gap_dagger_mappo": float(means.get("D_dagger", 0) - means.get("E_mappo", 0)),
        "gap_native_mappo": float(means.get("A_native", 0) - means.get("E_mappo", 0)),
    }
    (out_dir / "stage83_performance_gap_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
