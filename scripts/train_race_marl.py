#!/usr/bin/env python
"""Train a genuine MAPPO RACE-MARL policy (toy smoke or Casablanca)."""

from __future__ import annotations

import argparse
import json
import sys
import time
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
    parser.add_argument("--mode", choices=["smoke", "casablanca"], default="smoke")
    parser.add_argument("--iters", type=int, default=5)
    parser.add_argument("--steps", type=int, default=32)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--n-vehicles", type=int, default=3)
    parser.add_argument("--soc", type=float, default=0.35)
    parser.add_argument("--delay", type=float, default=0.0)
    parser.add_argument("--packet-loss", type=float, default=0.0)
    parser.add_argument("--ablation", default="F_race_marl")
    parser.add_argument("--eval-every", type=int, default=5)
    parser.add_argument("--eval-episodes", type=int, default=2)
    parser.add_argument("--max-decisions", type=int, default=400)
    parser.add_argument("--matched-send-p", type=float, default=None)
    parser.add_argument("--bc-cooperative", action="store_true")
    parser.add_argument("--bc-steps", type=int, default=256)
    parser.add_argument("--bc-epochs", type=int, default=25)
    parser.add_argument("--dagger-rounds", type=int, default=1)
    parser.add_argument("--freeze-comm", action="store_true")
    parser.add_argument("--stage", default="8.2")
    parser.add_argument(
        "--out",
        default="data/casablanca/online_results/marl_checkpoints/smoke.pt",
    )
    args = parser.parse_args()

    import torch
    from race_casablanca.marl.bc import (
        behavior_clone,
        collect_bc_batch,
        dagger_aggregate,
        evaluate_bc_accuracy,
    )
    from race_casablanca.marl.env import RaceMultiAgentEnv
    from race_casablanca.marl.mappo import MAPPOTrainer
    from race_casablanca.paths import project_root

    t0 = time.time()
    if args.mode == "smoke":
        factory = make_toy_factory(2)
        n_veh = 2
        soc = 1.0
        max_dec = 40
    else:
        from race_casablanca.marl.scenarios import load_casablanca_pool, make_pool_factory

        pool = load_casablanca_pool(split="train")
        factory = make_pool_factory(pool, n_vehicles=args.n_vehicles, procedural_jitter=True)
        n_veh = args.n_vehicles
        soc = args.soc
        max_dec = args.max_decisions

    env = RaceMultiAgentEnv(
        scenario_factory=factory,
        n_vehicles=n_veh,
        initial_soc=soc,
        message_delay_s=args.delay,
        packet_loss_p=args.packet_loss,
        ablation=args.ablation,
        seed=args.seed,
        max_decisions=max_dec,
        matched_send_p=args.matched_send_p,
    )
    trainer = MAPPOTrainer(env, freeze_comm=args.freeze_comm)
    before = {k: v.detach().clone() for k, v in trainer.actor.named_parameters()}

    bc_meta = None
    if args.bc_cooperative and args.mode == "casablanca":
        print(
            f"BC from RaceCooperative adapter: steps={args.bc_steps} epochs={args.bc_epochs}",
            flush=True,
        )
        batch = collect_bc_batch(
            env, n_steps=args.bc_steps, seed=args.seed + 50, teacher="cooperative"
        )
        losses = behavior_clone(
            trainer.actor, batch, epochs=args.bc_epochs, device=trainer.device
        )
        for r in range(max(0, args.dagger_rounds)):
            batch = dagger_aggregate(
                env,
                trainer.actor,
                n_steps=args.bc_steps // 2,
                seed=args.seed + 200 + r,
                device=trainer.device,
                prior_batch=batch,
            )
            losses = behavior_clone(
                trainer.actor, batch, epochs=max(5, args.bc_epochs // 2), device=trainer.device
            )
        bc_meta = evaluate_bc_accuracy(trainer.actor, batch, device=trainer.device)
        bc_meta["final_loss"] = float(losses[-1]) if losses else None
        print(f"  BC metrics: {bc_meta}", flush=True)

    best_path = None
    out = project_root() / args.out
    out.parent.mkdir(parents=True, exist_ok=True)

    def on_eval(i, ev, m):
        nonlocal best_path
        print(
            f"  eval iter={i+1} mean_ot={ev['mean_ot']:.3f} mean_return={ev['mean_return']:.3f}",
            flush=True,
        )
        if m.get("is_best"):
            best_path = out.with_name(out.stem + "_best.pt")
            trainer.save(best_path)
            print(f"  saved best -> {best_path}", flush=True)

    print(
        f"train mode={args.mode} ablation={args.ablation} seed={args.seed} "
        f"iters={args.iters} steps={args.steps} nv={n_veh} delay={args.delay} stage={args.stage}",
        flush=True,
    )
    logs = trainer.train(
        iterations=args.iters,
        steps_per_iter=args.steps,
        eval_every=args.eval_every if args.mode == "casablanca" else 0,
        eval_episodes=args.eval_episodes,
        on_eval=on_eval if args.mode == "casablanca" else None,
    )
    changed = any(not torch.allclose(before[k], v) for k, v in trainer.actor.named_parameters())
    eval_stats = trainer.evaluate_deterministic(n_episodes=max(2, args.eval_episodes))
    trainer.save(out)
    meta = {
        "mode": args.mode,
        "ablation": args.ablation,
        "seed": args.seed,
        "n_vehicles": n_veh,
        "initial_soc": soc,
        "message_delay_s": args.delay,
        "packet_loss_p": args.packet_loss,
        "matched_send_p": env.matched_send_p,
        "params_changed": changed,
        "n_updates": trainer.n_updates,
        "logs": logs,
        "eval": eval_stats,
        "bc": bc_meta,
        "checkpoint": str(out).replace("\\", "/"),
        "best_checkpoint": str(best_path).replace("\\", "/") if best_path else None,
        "torch": torch.__version__,
        "device": str(trainer.device),
        "wall_time_s": round(time.time() - t0, 2),
        "obs_dim": env.obs_dim,
        "n_op": env.n_op,
        "n_comm": env.n_comm,
        "stage": args.stage,
        "note": (
            "Stage smoke MAPPO on toy scenario."
            if args.mode == "smoke"
            else "Stage 8.2 MAPPO with cooperative BC init; bid-before-commit env."
        ),
    }
    meta_path = out.with_suffix(".json")
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(json.dumps({k: meta[k] for k in meta if k != "logs"}, indent=2), flush=True)
    if not changed:
        raise SystemExit("FAIL: actor parameters did not change — not real training")
    print(f"PASS training -> {out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
