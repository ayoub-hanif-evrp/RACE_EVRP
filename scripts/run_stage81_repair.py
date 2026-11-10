#!/usr/bin/env python
"""Stage 8.1: BC warm-start + corrected MAPPO recovery pilot (toy + Casablanca)."""

from __future__ import annotations

import json
import random
import sys
import time
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


def run_toy_recovery(out_dir: Path, seed: int = 0) -> dict:
    import torch
    from race_casablanca.marl.bc import behavior_clone, collect_bc_batch
    from race_casablanca.marl.env import RaceMultiAgentEnv
    from race_casablanca.marl.mappo import MAPPOTrainer
    from race_casablanca.marl.nets import FactorizedActor
    from race_casablanca.sim.synthetic import make_two_request_scenario

    def factory(seed: int = 0, n_vehicles: int = 2):
        sc = make_two_request_scenario()
        sc["fleet"] = {**sc["fleet"], "n_vehicles": n_vehicles}
        sc["scenario_id"] = f"toy-{seed}"
        return sc

    seed_all(seed)
    env = RaceMultiAgentEnv(
        scenario_factory=factory,
        n_vehicles=2,
        initial_soc=1.0,
        ablation="A_no_comm",
        seed=seed,
        max_decisions=40,
    )
    batch = collect_bc_batch(env, n_steps=128, seed=seed)
    actor = FactorizedActor(env.obs_dim, env.n_op, env.n_comm)
    bc_losses = behavior_clone(actor, batch, epochs=30, lr=1e-3)
    trainer = MAPPOTrainer(env, epochs=4)
    trainer.actor.load_state_dict(actor.state_dict())
    random_env = RaceMultiAgentEnv(
        scenario_factory=factory, n_vehicles=2, initial_soc=1.0, ablation="A_no_comm", seed=seed + 9, max_decisions=40
    )
    random_trainer = MAPPOTrainer(random_env, epochs=1)
    random_eval = random_trainer.evaluate_deterministic(n_episodes=4)
    bc_eval = trainer.evaluate_deterministic(n_episodes=4)
    logs = trainer.train(iterations=20, steps_per_iter=32, eval_every=5, eval_episodes=3)
    ft_eval = trainer.evaluate_deterministic(n_episodes=4)
    ckpt = out_dir / "marl_checkpoints" / f"stage81_toy_A_seed{seed}.pt"
    trainer.save(ckpt)
    return {
        "bc_loss_first": bc_losses[0],
        "bc_loss_last": bc_losses[-1],
        "random_ot": random_eval["mean_ot"],
        "bc_ot": bc_eval["mean_ot"],
        "finetune_ot": ft_eval["mean_ot"],
        "logs": logs,
        "checkpoint": str(ckpt).replace("\\", "/"),
    }


def run_casablanca_pilot(out_dir: Path, seed: int = 0) -> dict:
    import torch
    from race_casablanca.marl.bc import behavior_clone, collect_bc_batch
    from race_casablanca.marl.env import RaceMultiAgentEnv
    from race_casablanca.marl.mappo import MAPPOTrainer
    from race_casablanca.marl.nets import FactorizedActor
    from race_casablanca.marl.scenarios import (
        load_casablanca_pool,
        make_pool_factory,
        make_validation_factory,
    )

    seed_all(seed)
    train_pool = load_casablanca_pool(split="train")
    # Prefer lighter baseline scenarios for recovery pilot
    train_factory = make_pool_factory(
        train_pool,
        n_vehicles=3,
        name_filter=lambda n: n.startswith("baseline"),
        procedural_jitter=True,
    )
    val_pool = load_casablanca_pool(split="validation")
    val_factory = make_validation_factory(val_pool, n_vehicles=3)

    rows = []
    summaries = {}
    for abl in ("A_no_comm", "B_full_comm", "F_race_marl"):
        print(f"=== Casablanca pilot {abl} seed={seed} ===", flush=True)
        env = RaceMultiAgentEnv(
            scenario_factory=train_factory,
            n_vehicles=3,
            initial_soc=0.35,
            ablation=abl,
            seed=seed,
            max_decisions=200,
            message_delay_s=0.0,
        )
        batch = collect_bc_batch(env, n_steps=96, seed=seed)
        actor = FactorizedActor(env.obs_dim, env.n_op, env.n_comm)
        bc_losses = behavior_clone(actor, batch, epochs=25, lr=1e-3)
        trainer = MAPPOTrainer(env, epochs=4)
        trainer.actor.load_state_dict(actor.state_dict())

        best = {"mean_ot": -1.0}
        best_path = out_dir / "marl_checkpoints" / f"stage81_{abl}_seed{seed}_best.pt"

        def on_eval(i, ev, m, _abl=abl):
            nonlocal best
            print(f"  {_abl} eval iter={i+1} ot={ev['mean_ot']:.3f}", flush=True)
            if m.get("is_best") and ev["mean_ot"] >= best["mean_ot"]:
                best = dict(ev)
                trainer.save(best_path)

        # Validation-side checkpoint selection: temporarily swap factory
        def val_on_eval(i, ev, m):
            # Re-evaluate on validation factory
            old = trainer.env.scenario_factory
            trainer.env.scenario_factory = val_factory
            vev = trainer.evaluate_deterministic(n_episodes=2)
            trainer.env.scenario_factory = old
            m["val_eval"] = vev
            on_eval(i, vev, {**m, "is_best": vev["mean_ot"] >= best["mean_ot"]})

        logs = trainer.train(
            iterations=25,
            steps_per_iter=48,
            eval_every=5,
            eval_episodes=2,
            on_eval=val_on_eval,
        )
        final_path = out_dir / "marl_checkpoints" / f"stage81_{abl}_seed{seed}.pt"
        trainer.save(final_path)

        # Delay stress for F
        delay_ot = None
        if abl == "F_race_marl":
            delay_env = RaceMultiAgentEnv(
                scenario_factory=val_factory,
                n_vehicles=3,
                initial_soc=0.35,
                ablation=abl,
                seed=seed,
                max_decisions=200,
                message_delay_s=30.0,
            )
            delay_trainer = MAPPOTrainer(delay_env)
            load_path = best_path if best_path.exists() else final_path
            delay_trainer.load(load_path)
            delay_stats = delay_trainer.evaluate_deterministic(n_episodes=2)
            delay_ot = delay_stats["mean_ot"]
            delay_sends = delay_env._n_send_actions
        else:
            delay_sends = None

        summaries[abl] = {
            "bc_loss_last": bc_losses[-1],
            "best_val_ot": best.get("mean_ot"),
            "final_train_side_ot": (logs[-1].get("eval") or {}).get("mean_ot"),
            "delay30_ot": delay_ot,
            "delay30_sends": delay_sends,
            "checkpoint": str(final_path).replace("\\", "/"),
            "best_checkpoint": str(best_path).replace("\\", "/") if best_path.exists() else None,
            "n_updates": trainer.n_updates,
        }
        rows.append({"ablation": abl, **{k: summaries[abl][k] for k in summaries[abl] if k != "checkpoint"}})
    pd.DataFrame(rows).to_csv(out_dir / "stage81_casablanca_pilot.csv", index=False)
    return summaries


def main() -> int:
    from race_casablanca.paths import project_root

    t0 = time.time()
    out_dir = project_root() / "data" / "casablanca" / "online_results"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "marl_checkpoints").mkdir(parents=True, exist_ok=True)

    print("=== Toy recovery ===", flush=True)
    toy = run_toy_recovery(out_dir, seed=0)
    print(json.dumps({k: toy[k] for k in toy if k != "logs"}, indent=2), flush=True)

    print("=== Casablanca pilot ===", flush=True)
    casa = run_casablanca_pilot(out_dir, seed=0)

    summary = {
        "stage": "8.1",
        "wall_time_s": round(time.time() - t0, 2),
        "toy": {k: toy[k] for k in toy if k != "logs"},
        "casablanca": casa,
        "note": (
            "Stage 8.1 corrected factorized MAPPO + BC warm-start. "
            "Prior Stage 8 ablation CSVs are historical/invalid for final method claims."
        ),
    }
    path = out_dir / "stage81_summary.json"
    path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)
    print(f"Wrote {path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
