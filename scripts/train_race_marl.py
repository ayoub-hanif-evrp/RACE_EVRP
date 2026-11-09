#!/usr/bin/env python
"""Train a genuine MAPPO RACE-MARL policy (smoke / small runs)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def make_toy_factory(n_vehicles: int = 2):
    from race_casablanca.sim.synthetic import make_two_request_scenario

    def factory(seed: int = 0, n_vehicles: int = n_vehicles):
        sc = make_two_request_scenario()
        sc["fleet"] = {**sc["fleet"], "n_vehicles": n_vehicles}
        sc["scenario_id"] = f"toy-{seed}"
        return sc

    return factory


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iters", type=int, default=5)
    parser.add_argument("--steps", type=int, default=32)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out", default="data/casablanca/online_results/marl_checkpoints/smoke.pt")
    args = parser.parse_args()

    import torch
    from race_casablanca.marl.env import RaceMultiAgentEnv
    from race_casablanca.marl.mappo import MAPPOTrainer
    from race_casablanca.paths import project_root

    env = RaceMultiAgentEnv(
        scenario_factory=make_toy_factory(2),
        n_vehicles=2,
        initial_soc=1.0,
        message_delay_s=0.0,
        comm_enabled=True,
        seed=args.seed,
        max_decisions=40,
    )
    trainer = MAPPOTrainer(env)
    # Prove parameters change
    before = {k: v.detach().clone() for k, v in trainer.actor.named_parameters()}
    logs = trainer.train(iterations=args.iters, steps_per_iter=args.steps)
    changed = False
    for k, v in trainer.actor.named_parameters():
        if not torch.allclose(before[k], v):
            changed = True
            break
    eval_stats = trainer.evaluate_deterministic(n_episodes=2)
    out = project_root() / args.out
    trainer.save(out)
    meta = {
        "params_changed": changed,
        "n_updates": trainer.n_updates,
        "logs": logs,
        "eval": eval_stats,
        "checkpoint": str(out).replace("\\", "/"),
        "torch": torch.__version__,
        "note": "Genuine MAPPO smoke training on toy synthetic scenario.",
    }
    meta_path = out.with_suffix(".json")
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(json.dumps(meta, indent=2))
    if not changed:
        raise SystemExit("FAIL: actor parameters did not change — not real training")
    print(f"PASS smoke training -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
