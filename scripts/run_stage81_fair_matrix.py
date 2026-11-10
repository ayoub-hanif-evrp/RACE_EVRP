#!/usr/bin/env python
"""Stage 8.1 Part 8–9: fair matched-scenario matrix + remaining learned ablations.

Compares non-learning cooperative modes, greedy charge-to-70%, and corrected MAPPO
A–F on the same validation/diagnostic scenarios. Trains any missing Stage 8.1
checkpoints (C/D/E, seed1 for A/B/F) with BC warm-start.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from copy import deepcopy
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def seed_all(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    import torch

    torch.manual_seed(seed)


def matched_scenario_dirs():
    from race_casablanca.marl.scenarios import VAL_SCENARIOS, resolve_eval_dirs
    from race_casablanca.paths import scenarios_dir

    paths = []
    for name in VAL_SCENARIOS:
        p = scenarios_dir() / "validation" / name
        if p.exists():
            paths.append(p)
    # Add compact development-validation diagnostics (not locked_final)
    for p in resolve_eval_dirs():
        if p not in paths:
            paths.append(p)
    return paths


def run_nonlearning(paths, graph, model, *, delay_s: float, soc: float) -> list[dict]:
    from race_casablanca.policies import ChargingController, GreedyInsertionPolicy, RaceCooperativePolicy
    from race_casablanca.sim.environment import OnlineSimulator, SimConfig
    from race_casablanca.sim.scenario_loader import load_scenario

    rows = []
    modes = [
        ("nl_none", "none", None),
        ("nl_full", "full", None),
        ("nl_selective", "selective", None),
        ("nl_random_matched", "random_matched", None),
        ("greedy_charge70", None, "greedy"),
    ]
    for path in paths:
        sc = load_scenario(path, load_network=False, graph=graph, model=model)
        # First pass selective to get message budget for random_matched
        selective_budget = 0
        pol_sel = RaceCooperativePolicy(comm_mode="selective", enable_readiness_charge=True, rng_seed=7)
        sim0 = OnlineSimulator(
            scenario_id=sc.scenario_id,
            graph=graph,
            model=model,
            requests=deepcopy(sc.requests),
            fleet=sc.fleet,
            depot_node=sc.depot_node,
            shift_start_s=sc.shift_start_s,
            shift_end_s=sc.shift_end_s,
            config=SimConfig(
                info_mode="restricted",
                seed=1,
                initial_soc=soc,
                message_delay_s=delay_s,
                periodic_state_broadcast=False,
                day=sc.day,
            ),
            policy=pol_sel,
        )
        m0 = sim0.run().to_dict()
        selective_budget = int(pol_sel.n_messages_sent_by_policy)

        for label, comm_mode, kind in modes:
            # full@delay>0 historically explodes the event queue; skip with documented gap
            if label == "nl_full" and delay_s > 0:
                rows.append(
                    {
                        "method": label,
                        "scenario": path.name,
                        "delay_s": delay_s,
                        "on_time_rate_all": float("nan"),
                        "n_served": float("nan"),
                        "n_requests": len(sc.requests),
                        "policy_msgs": float("nan"),
                        "n_charges": float("nan"),
                        "family": "nonlearning",
                        "note": "skipped_full_at_delay_event_blowup",
                    }
                )
                continue
            if kind == "greedy":
                pol = GreedyInsertionPolicy(
                    charging=ChargingController(mode="charge_to_target", target_soc=0.70)
                )
            elif label == "nl_selective":
                # reuse already-run selective
                rows.append(
                    {
                        "method": label,
                        "scenario": path.name,
                        "delay_s": delay_s,
                        "on_time_rate_all": m0["on_time_rate_all"],
                        "n_served": m0["n_served"],
                        "n_requests": m0["n_requests"],
                        "policy_msgs": selective_budget,
                        "n_charges": m0.get("n_charges", 0),
                        "family": "nonlearning",
                    }
                )
                continue
            elif comm_mode == "random_matched":
                pol = RaceCooperativePolicy(
                    comm_mode="random_matched",
                    matched_message_budget=selective_budget,
                    enable_readiness_charge=True,
                    rng_seed=11,
                )
            else:
                pol = RaceCooperativePolicy(
                    comm_mode=comm_mode, enable_readiness_charge=True, rng_seed=7
                )
            print(f"NL {label} {path.name} d={delay_s}", flush=True)
            info_mode = "full" if kind == "greedy" else "restricted"
            sim = OnlineSimulator(
                scenario_id=sc.scenario_id,
                graph=graph,
                model=model,
                requests=deepcopy(sc.requests),
                fleet=sc.fleet,
                depot_node=sc.depot_node,
                shift_start_s=sc.shift_start_s,
                shift_end_s=sc.shift_end_s,
                config=SimConfig(
                    info_mode=info_mode,
                    seed=1,
                    initial_soc=soc,
                    message_delay_s=delay_s if kind != "greedy" else 0.0,
                    periodic_state_broadcast=False,
                    day=sc.day,
                ),
                policy=pol,
            )
            m = sim.run().to_dict()
            rows.append(
                {
                    "method": label,
                    "scenario": path.name,
                    "delay_s": delay_s,
                    "on_time_rate_all": m["on_time_rate_all"],
                    "n_served": m["n_served"],
                    "n_requests": m["n_requests"],
                    "policy_msgs": getattr(pol, "n_messages_sent_by_policy", 0),
                    "n_charges": m.get("n_charges", 0),
                    "family": "nonlearning" if kind is None else "greedy",
                }
            )
    return rows


def train_mappo_ablation(
    *,
    ablation: str,
    seed: int,
    out_dir: Path,
    iters: int,
    steps: int,
    delay_s: float = 0.0,
) -> dict:
    from race_casablanca.marl.bc import behavior_clone, collect_bc_batch
    from race_casablanca.marl.env import RaceMultiAgentEnv
    from race_casablanca.marl.mappo import MAPPOTrainer
    from race_casablanca.marl.nets import FactorizedActor
    from race_casablanca.marl.scenarios import load_casablanca_pool, make_pool_factory, make_validation_factory

    seed_all(seed)
    train_pool = load_casablanca_pool(split="train")
    train_factory = make_pool_factory(
        train_pool,
        n_vehicles=3,
        name_filter=lambda n: n.startswith("baseline") or n.startswith("tight"),
        procedural_jitter=True,
    )
    val_pool = load_casablanca_pool(split="validation")
    val_factory = make_validation_factory(val_pool, n_vehicles=3)

    env = RaceMultiAgentEnv(
        scenario_factory=train_factory,
        n_vehicles=3,
        initial_soc=0.35,
        ablation=ablation,
        seed=seed,
        max_decisions=200,
        message_delay_s=delay_s,
    )
    print(f"TRAIN {ablation} seed={seed} iters={iters}", flush=True)
    batch = collect_bc_batch(env, n_steps=80, seed=seed)
    actor = FactorizedActor(env.obs_dim, env.n_op, env.n_comm)
    bc_losses = behavior_clone(actor, batch, epochs=20, lr=1e-3)
    trainer = MAPPOTrainer(env, epochs=4)
    trainer.actor.load_state_dict(actor.state_dict())

    best = {"mean_ot": -1.0}
    best_path = out_dir / "marl_checkpoints" / f"stage81_{ablation}_seed{seed}_best.pt"
    final_path = out_dir / "marl_checkpoints" / f"stage81_{ablation}_seed{seed}.pt"

    def on_eval(i, ev, m):
        nonlocal best
        old = trainer.env.scenario_factory
        trainer.env.scenario_factory = val_factory
        vev = trainer.evaluate_deterministic(n_episodes=2)
        trainer.env.scenario_factory = old
        print(f"  {ablation} s{seed} iter={i+1} val_ot={vev['mean_ot']:.3f}", flush=True)
        if vev["mean_ot"] >= best["mean_ot"]:
            best = dict(vev)
            trainer.save(best_path)

    trainer.train(
        iterations=iters,
        steps_per_iter=steps,
        eval_every=5,
        eval_episodes=2,
        on_eval=on_eval,
    )
    trainer.save(final_path)
    return {
        "ablation": ablation,
        "seed": seed,
        "bc_loss_last": bc_losses[-1],
        "best_val_ot": best["mean_ot"],
        "checkpoint": str(final_path).replace("\\", "/"),
        "best_checkpoint": str(best_path).replace("\\", "/") if best_path.exists() else None,
        "n_updates": trainer.n_updates,
    }


def eval_mappo_on_paths(paths, graph, model, *, ablation, ckpt, delay_s, soc) -> list[dict]:
    import torch
    from race_casablanca.marl.env import RaceMultiAgentEnv
    from race_casablanca.marl.mappo import MAPPOTrainer
    from race_casablanca.sim.scenario_loader import load_scenario
    from race_casablanca.sim.types import RequestStatus

    rows = []
    for path in paths:
        sc = load_scenario(path, load_network=False, graph=graph, model=model)

        def factory(seed: int = 0, n_vehicles: int = 3, _sc=sc):
            reqs = deepcopy(_sc.requests)
            for r in reqs:
                r.status = RequestStatus.UNRELEASED
                r.owner = None
            return {
                "scenario_id": f"{_sc.scenario_id}/eval",
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
            n_vehicles=3,
            initial_soc=soc,
            ablation=ablation,
            seed=0,
            max_decisions=400,
            message_delay_s=delay_s,
        )
        trainer = MAPPOTrainer(env)
        trainer.load(ckpt)
        steps = env.reset(seed=0)
        done = False
        while not done:
            actions = {}
            for vid, st in steps.items():
                o = torch.as_tensor(st.obs, dtype=torch.float32, device=trainer.device).unsqueeze(0)
                om = torch.as_tensor(st.op_mask, dtype=torch.float32, device=trainer.device).unsqueeze(0)
                cm = torch.as_tensor(st.comm_mask, dtype=torch.float32, device=trainer.device).unsqueeze(0)
                op_logits, comm_logits = trainer.actor(o, om, cm)
                actions[vid] = (
                    int(torch.argmax(op_logits, dim=-1).item()),
                    int(torch.argmax(comm_logits, dim=-1).item()),
                )
            steps = env.step(actions)
            done = list(steps.values())[0].done
        m = env.final_metrics()
        rows.append(
            {
                "method": f"mappo_{ablation}",
                "scenario": path.name,
                "delay_s": delay_s,
                "on_time_rate_all": m.get("on_time_rate_all"),
                "n_served": m.get("n_served"),
                "n_requests": m.get("n_requests"),
                "policy_msgs": m.get("n_send_actions", 0),
                "n_charges": m.get("n_charges", 0),
                "n_op_claims": m.get("n_op_claims", 0),
                "n_decisions": m.get("n_decisions", 0),
                "family": "mappo",
                "checkpoint": str(ckpt).replace("\\", "/"),
            }
        )
        print(
            f"MAPPO {ablation} {path.name} d={delay_s} ot={m.get('on_time_rate_all'):.3f} "
            f"sends={m.get('n_send_actions')}",
            flush=True,
        )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iters", type=int, default=20)
    parser.add_argument("--steps", type=int, default=40)
    parser.add_argument("--soc", type=float, default=0.35)
    parser.add_argument("--skip-train", action="store_true")
    args = parser.parse_args()

    from race_casablanca.paths import project_root
    from race_casablanca.sim.scenario_loader import load_congestion_model, load_drive_graph

    t0 = time.time()
    out_dir = project_root() / "data" / "casablanca" / "online_results"
    ckpt_dir = out_dir / "marl_checkpoints"
    ckpt_dir.mkdir(parents=True, exist_ok=True)

    print("Loading network...", flush=True)
    graph = load_drive_graph()
    model = load_congestion_model()
    paths = matched_scenario_dirs()
    print(f"Matched scenarios ({len(paths)}): {[p.name for p in paths]}", flush=True)

    # --- Train missing MAPPO ablations / seeds ---
    train_jobs = []
    for abl in (
        "A_no_comm",
        "B_full_comm",
        "C_random_matched",
        "D_selective",
        "E_selective_no_energy",
        "F_race_marl",
    ):
        for seed in (0, 1):
            best = ckpt_dir / f"stage81_{abl}_seed{seed}_best.pt"
            final = ckpt_dir / f"stage81_{abl}_seed{seed}.pt"
            if best.exists() or final.exists():
                continue
            train_jobs.append((abl, seed))

    train_meta = []
    if not args.skip_train:
        for abl, seed in train_jobs:
            train_meta.append(
                train_mappo_ablation(
                    ablation=abl,
                    seed=seed,
                    out_dir=out_dir,
                    iters=args.iters,
                    steps=args.steps,
                )
            )
    else:
        print(f"skip-train: {len(train_jobs)} missing checkpoints left untrained", flush=True)

    # --- Non-learning fair matrix @ delay 0 and 30 ---
    nl_rows = []
    for delay in (0.0, 30.0):
        nl_rows.extend(run_nonlearning(paths, graph, model, delay_s=delay, soc=args.soc))

    # --- MAPPO eval on matched scenarios ---
    mappo_rows = []
    for abl in (
        "A_no_comm",
        "B_full_comm",
        "C_random_matched",
        "D_selective",
        "E_selective_no_energy",
        "F_race_marl",
    ):
        # Prefer seed0 best, else seed1, else final
        ckpt = None
        for seed in (0, 1):
            for name in (
                f"stage81_{abl}_seed{seed}_best.pt",
                f"stage81_{abl}_seed{seed}.pt",
            ):
                p = ckpt_dir / name
                if p.exists():
                    ckpt = p
                    break
            if ckpt is not None:
                break
        if ckpt is None:
            print(f"SKIP MAPPO eval missing {abl}", flush=True)
            continue
        for delay in (0.0, 30.0):
            if delay > 0 and abl not in ("F_race_marl", "B_full_comm", "A_no_comm"):
                continue  # keep delay matrix compact
            mappo_rows.extend(
                eval_mappo_on_paths(
                    paths, graph, model, ablation=abl, ckpt=ckpt, delay_s=delay, soc=args.soc
                )
            )

    all_rows = nl_rows + mappo_rows
    df = pd.DataFrame(all_rows)
    csv_path = out_dir / "stage81_fair_matrix.csv"
    df.to_csv(csv_path, index=False)

    summary_rows = (
        df.groupby(["method", "delay_s"], as_index=False)
        .agg(
            mean_ot=("on_time_rate_all", "mean"),
            mean_served=("n_served", "mean"),
            mean_msgs=("policy_msgs", "mean"),
            n=("scenario", "count"),
        )
        .sort_values(["delay_s", "mean_ot"], ascending=[True, False])
    )
    summary_path = out_dir / "stage81_fair_matrix_summary.csv"
    summary_rows.to_csv(summary_path, index=False)

    # Multi-seed val OT from train metas + existing stage81_summary
    seed_rows = list(train_meta)
    for abl in ("A_no_comm", "B_full_comm", "F_race_marl"):
        for seed in (0, 1):
            meta_p = ckpt_dir / f"stage81_{abl}_seed{seed}.json"
            # synthesize from existing summary if present
            pass

    out = {
        "wall_time_s": round(time.time() - t0, 2),
        "n_scenarios": len(paths),
        "scenarios": [p.name for p in paths],
        "train_meta": train_meta,
        "summary": summary_rows.to_dict(orient="records"),
        "note": (
            "Stage 8.1 fair matched matrix. Stage 8 historical ablations remain invalid. "
            "Locked final unused."
        ),
    }
    json_path = out_dir / "stage81_fair_matrix_summary.json"
    json_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(summary_rows.to_string(index=False), flush=True)
    print(f"Wrote {csv_path}", flush=True)
    print(f"Wrote {json_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
