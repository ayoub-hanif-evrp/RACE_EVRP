#!/usr/bin/env python
"""Stage 8.3 controlled recovery: native-bridge BC → DAgger → val-selected MAPPO."""

from __future__ import annotations

import argparse
import json
import sys
import time
from copy import deepcopy
from pathlib import Path

import pandas as pd
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def eval_on_paths(actor, paths, graph, model, *, ablation: str, n_vehicles: int):
    from race_casablanca.marl.env import RaceMultiAgentEnv
    from race_casablanca.sim.scenario_loader import load_scenario
    from race_casablanca.sim.types import RequestStatus

    rows = []
    for path in paths:
        sc = load_scenario(path, load_network=False, graph=graph, model=model)
        reqs0 = deepcopy(sc.requests)

        def factory(seed=0, n_vehicles=n_vehicles, _reqs0=reqs0, _sc=sc):
            reqs = deepcopy(_reqs0)
            for r in reqs:
                r.status = RequestStatus.UNRELEASED
                r.owner = None
            return {
                "scenario_id": _sc.scenario_id,
                "graph": graph,
                "model": model,
                "requests": reqs,
                "fleet": {**_sc.fleet, "n_vehicles": n_vehicles},
                "depot_node": _sc.depot_node,
                "shift_start_s": _sc.shift_start_s,
                "shift_end_s": _sc.shift_end_s,
                "day": getattr(_sc, "day", "Monday"),
            }

        env = RaceMultiAgentEnv(
            scenario_factory=factory,
            n_vehicles=n_vehicles,
            ablation=ablation,
            seed=0,
            max_decisions=2000,
            initial_soc=0.35,
        )
        steps = env.reset(seed=0)
        while True:
            actions = {}
            for vid, st in steps.items():
                with torch.no_grad():
                    o = torch.as_tensor(st.obs).unsqueeze(0)
                    om = torch.as_tensor(st.op_mask).unsqueeze(0)
                    cm = torch.as_tensor(st.comm_mask).unsqueeze(0)
                    op_l, c_l = actor(o, om, cm)
                    actions[vid] = (int(op_l.argmax(-1)), int(c_l.argmax(-1)))
            steps = env.step(actions)
            if list(steps.values())[0].done:
                break
        m = env.final_metrics()
        rows.append(
            {
                "scenario": path.name,
                "ablation": ablation,
                "ot": m.get("on_time_rate_all"),
                "n_bid_bytes": m.get("n_bid_bytes"),
                "n_bid_messages": m.get("n_bid_messages"),
                "n_decisions": m.get("n_decisions"),
            }
        )
    return pd.DataFrame(rows)


def eval_teacher_intent(paths, graph, model, *, ablation: str, n_vehicles: int):
    from race_casablanca.marl.bc import NativeBridgeTeacher
    from race_casablanca.marl.env import RaceMultiAgentEnv
    from race_casablanca.sim.scenario_loader import load_scenario
    from race_casablanca.sim.types import RequestStatus

    rows = []
    teacher = NativeBridgeTeacher(mode="intent")
    for path in paths:
        sc = load_scenario(path, load_network=False, graph=graph, model=model)
        reqs0 = deepcopy(sc.requests)

        def factory(seed=0, n_vehicles=n_vehicles, _reqs0=reqs0, _sc=sc):
            reqs = deepcopy(_reqs0)
            for r in reqs:
                r.status = RequestStatus.UNRELEASED
                r.owner = None
            return {
                "scenario_id": _sc.scenario_id,
                "graph": graph,
                "model": model,
                "requests": reqs,
                "fleet": {**_sc.fleet, "n_vehicles": n_vehicles},
                "depot_node": _sc.depot_node,
                "shift_start_s": _sc.shift_start_s,
                "shift_end_s": _sc.shift_end_s,
                "day": getattr(_sc, "day", "Monday"),
            }

        env = RaceMultiAgentEnv(
            scenario_factory=factory,
            n_vehicles=n_vehicles,
            ablation=ablation,
            seed=0,
            max_decisions=2000,
            initial_soc=0.35,
        )
        teacher.reset()
        steps = env.reset(seed=0)
        while True:
            labels = teacher.actions(env)
            steps = env.step(labels)
            if list(steps.values())[0].done:
                break
        m = env.final_metrics()
        rows.append(
            {
                "scenario": path.name,
                "ablation": ablation,
                "ot": m.get("on_time_rate_all"),
                "n_bid_bytes": m.get("n_bid_bytes"),
                "n_bid_messages": m.get("n_bid_messages"),
                "n_decisions": m.get("n_decisions"),
            }
        )
    return pd.DataFrame(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", type=int, nargs="+", default=[0, 1, 2])
    parser.add_argument("--bc-steps", type=int, default=800)
    parser.add_argument("--bc-epochs", type=int, default=80)
    parser.add_argument("--dagger-steps", type=int, default=400)
    parser.add_argument("--mappo-iters", type=int, default=20)
    parser.add_argument("--steps", type=int, default=48)
    parser.add_argument("--n-vehicles", type=int, default=3)
    args = parser.parse_args()

    from race_casablanca.marl.bc import (
        behavior_clone,
        collect_bc_batch,
        dagger_aggregate,
        evaluate_bc_accuracy,
    )
    from race_casablanca.marl.env import (
        ABLATION_A,
        ABLATION_C,
        ABLATION_D,
        ABLATION_E,
        ABLATION_F,
        RaceMultiAgentEnv,
    )
    from race_casablanca.marl.mappo import MAPPOTrainer
    from race_casablanca.marl.nets import FactorizedActor
    from race_casablanca.marl.scenarios import load_casablanca_pool, make_pool_factory, resolve_eval_dirs
    from race_casablanca.paths import project_root
    from race_casablanca.sim.scenario_loader import load_congestion_model, load_drive_graph

    root = project_root()
    out = root / "data" / "casablanca" / "online_results"
    ckpt_dir = out / "stage83_checkpoints"
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    graph = load_drive_graph()
    model = load_congestion_model()
    val_paths = resolve_eval_dirs()

    pool = load_casablanca_pool(split="train")
    train_factory = make_pool_factory(pool, n_vehicles=args.n_vehicles, procedural_jitter=True)
    matched_p = 0.3074
    mp = out / "stage82_matched_send_p.json"
    if mp.exists():
        matched_p = float(json.loads(mp.read_text(encoding="utf-8"))["matched_send_p"])

    t0 = time.time()
    all_rows = []

    print("=== teacher intent baseline ===", flush=True)
    df_t = eval_teacher_intent(val_paths, graph, model, ablation=ABLATION_D, n_vehicles=args.n_vehicles)
    df_t["seed"] = -1
    df_t["stage"] = "teacher_intent"
    all_rows.append(df_t)
    print("teacher_intent mean OT", df_t["ot"].mean(), flush=True)

    for seed in args.seeds:
        print(f"=== seed {seed}: native-bridge BC ===", flush=True)
        env = RaceMultiAgentEnv(
            scenario_factory=train_factory,
            n_vehicles=args.n_vehicles,
            ablation=ABLATION_D,
            seed=seed,
            max_decisions=400,
            matched_send_p=matched_p,
        )
        batch = collect_bc_batch(
            env, n_steps=args.bc_steps, seed=seed + 50, teacher="native_bridge"
        )
        actor = FactorizedActor(env.obs_dim, env.n_op, env.n_comm)
        behavior_clone(actor, batch, epochs=args.bc_epochs, device="cpu", class_weight=True)
        acc = evaluate_bc_accuracy(actor, batch)
        print("BC acc", acc, flush=True)

        print(f"=== seed {seed}: native-bridge DAgger ===", flush=True)
        batch = dagger_aggregate(
            env,
            actor,
            n_steps=args.dagger_steps,
            seed=seed + 90,
            prior_batch=batch,
            teacher="native_bridge",
        )
        behavior_clone(actor, batch, epochs=args.bc_epochs // 2, device="cpu", class_weight=True)
        acc_d = evaluate_bc_accuracy(actor, batch)
        print("DAgger acc", acc_d, flush=True)

        df_bc = eval_on_paths(
            actor, val_paths, graph, model, ablation=ABLATION_D, n_vehicles=args.n_vehicles
        )
        df_bc["seed"] = seed
        df_bc["stage"] = "bc_dagger_native_bridge"
        all_rows.append(df_bc)
        print("BC+DAgger mean OT", df_bc["ot"].mean(), flush=True)
        torch.save(
            {"actor": actor.state_dict(), "acc": acc, "acc_dagger": acc_d, "seed": seed},
            ckpt_dir / f"stage83_bc_dagger_seed{seed}.pt",
        )

        print(f"=== seed {seed}: MAPPO A freeze_comm val-select ===", flush=True)
        env_a = RaceMultiAgentEnv(
            scenario_factory=train_factory,
            n_vehicles=args.n_vehicles,
            ablation=ABLATION_A,
            seed=seed,
            max_decisions=400,
        )
        tr = MAPPOTrainer(env_a, freeze_comm=True)
        tr.actor.load_state_dict(actor.state_dict())
        best_ot, best_state = -1.0, None
        for i in range(args.mappo_iters):
            buf, boot, _ = tr.collect(args.steps)
            tr.update(buf, last_value=boot)
            if (i + 1) % 5 == 0:
                dfv = eval_on_paths(
                    tr.actor, val_paths[:2], graph, model, ablation=ABLATION_A, n_vehicles=args.n_vehicles
                )
                ot = float(dfv["ot"].mean())
                print(f"  val@{i+1} ot={ot:.3f}", flush=True)
                if ot >= best_ot:
                    best_ot = ot
                    best_state = {k: v.detach().cpu().clone() for k, v in tr.actor.state_dict().items()}
        if best_state:
            tr.actor.load_state_dict(best_state)
        tr.save(ckpt_dir / f"stage83_A_seed{seed}.pt")

        for abl, label in [
            (ABLATION_A, "mappo_A"),
            (ABLATION_F, "mappo_F"),
            (ABLATION_C, "mappo_C"),
            (ABLATION_E, "mappo_E"),
            (ABLATION_D, "mappo_D"),
        ]:
            if abl != ABLATION_A:
                env_x = RaceMultiAgentEnv(
                    scenario_factory=train_factory,
                    n_vehicles=args.n_vehicles,
                    ablation=abl,
                    seed=seed,
                    max_decisions=400,
                    matched_send_p=matched_p,
                )
                trx = MAPPOTrainer(env_x)
                trx.actor.load_state_dict(tr.actor.state_dict())
                best_ot, best_state = -1.0, None
                for i in range(10):
                    buf, boot, _ = trx.collect(args.steps)
                    trx.update(buf, last_value=boot)
                    if (i + 1) % 5 == 0:
                        dfv = eval_on_paths(
                            trx.actor, val_paths[:2], graph, model, ablation=abl, n_vehicles=args.n_vehicles
                        )
                        ot = float(dfv["ot"].mean())
                        if ot >= best_ot:
                            best_ot = ot
                            best_state = {
                                k: v.detach().cpu().clone() for k, v in trx.actor.state_dict().items()
                            }
                if best_state:
                    trx.actor.load_state_dict(best_state)
                eval_actor = trx.actor
                trx.save(ckpt_dir / f"stage83_{abl}_seed{seed}.pt")
            else:
                eval_actor = tr.actor
            df = eval_on_paths(
                eval_actor, val_paths, graph, model, ablation=abl, n_vehicles=args.n_vehicles
            )
            df["seed"] = seed
            df["stage"] = label
            all_rows.append(df)
            print(label, "mean OT", df["ot"].mean(), flush=True)

    big = pd.concat(all_rows, ignore_index=True)
    big.to_csv(out / "stage83_recovery_study.csv", index=False)
    summary = (
        big.groupby("stage")[["ot", "n_bid_bytes", "n_bid_messages"]]
        .agg(["mean", "std"])
        .reset_index()
    )
    summary.columns = ["_".join(c).strip("_") for c in summary.columns.values]
    summary.to_csv(out / "stage83_recovery_summary_table.csv", index=False)
    js = {
        "by_stage": big.groupby("stage")["ot"].agg(["mean", "std", "count"]).reset_index().to_dict(orient="records"),
        "matched_send_p": matched_p,
        "seeds": list(args.seeds),
        "bc_steps": args.bc_steps,
        "bc_epochs": args.bc_epochs,
        "dagger_steps": args.dagger_steps,
        "mappo_iters": args.mappo_iters,
        "wall_time_s": time.time() - t0,
        "checkpoint_selection": "validation OT on first 2 development scenarios every 5 MAPPO iters",
    }
    (out / "stage83_recovery_summary.json").write_text(json.dumps(js, indent=2), encoding="utf-8")
    print(json.dumps(js, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
