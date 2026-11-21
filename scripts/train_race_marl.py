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
    parser.add_argument("--bc-cooperative", action="store_true", help="BC from cooperative adapter")
    parser.add_argument(
        "--bc-native",
        action="store_true",
        help="BC from native RaceCooperativePolicy execute teacher (Phase 1 / G1)",
    )
    parser.add_argument("--bc-steps", type=int, default=256)
    parser.add_argument("--bc-epochs", type=int, default=25)
    parser.add_argument("--dagger-rounds", type=int, default=1)
    parser.add_argument(
        "--bc-comm-mode",
        choices=["selective", "full"],
        default="selective",
        help="Native teacher comm_mode for BC/DAgger labels (full warms F toward B)",
    )
    parser.add_argument("--freeze-comm", action="store_true")
    parser.add_argument(
        "--freeze-op",
        action="store_true",
        help="Freeze operational PPO head (protect BC claim policy; tune comm only)",
    )
    parser.add_argument("--lr", type=float, default=3e-4, help="MAPPO Adam LR")
    parser.add_argument("--msg-cost", type=float, default=None, help="Override Phase-3 msg reward cost")
    parser.add_argument("--byte-cost", type=float, default=None, help="Override Phase-3 byte reward cost")
    parser.add_argument("--stage", default="8.2")
    parser.add_argument(
        "--episode-source",
        choices=["solomon_style", "procedural", "fixed_pool"],
        default="solomon_style",
        help="solomon_style = C/R/RC × 15/30/45 (recommended); procedural = legacy regimes",
    )
    parser.add_argument(
        "--curriculum",
        choices=["round_robin", "baseline_only", "peak_only", "tight_only", "conflict_only"],
        default="round_robin",
    )
    parser.add_argument(
        "--energy-binding",
        action="store_true",
        help="Alternate mid/low SOC episodes (Phase-2 energy-binding tier)",
    )
    parser.add_argument(
        "--phase3",
        action="store_true",
        help="Preset: casablanca procedural round_robin, bc-native, F ablation, Phase-3 reward",
    )
    parser.add_argument(
        "--out",
        default="data/casablanca/online_results/marl_checkpoints/smoke.pt",
    )
    parser.add_argument(
        "--resume",
        default=None,
        help="Load actor/critic from checkpoint before BC/MAPPO (Phase 3 fine-tune)",
    )
    parser.add_argument(
        "--skip-bc",
        action="store_true",
        help="Skip BC/DAgger (use with --resume for on-policy fine-tune)",
    )
    args = parser.parse_args()
    if args.phase3:
        args.mode = "casablanca"
        args.episode_source = "procedural"
        # Default curriculum is round_robin (baseline for G2 + conflict for G3/G4).
        # Override with --curriculum conflict_only and/or --energy-binding for stress.
        args.bc_native = True
        args.ablation = "F_race_marl"
        args.stage = "phase3"
        if args.out.endswith("smoke.pt"):
            args.out = "data/casablanca/online_results/top_tier/marl_checkpoints/phase3_F_seed0.pt"

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
        from race_casablanca.marl.scenarios import make_training_factory

        factory = make_training_factory(
            source=args.episode_source,
            master_seed=args.seed,
            n_vehicles=args.n_vehicles,
            curriculum=args.curriculum,
            procedural_jitter=True,
            energy_binding=bool(args.energy_binding),
        )
        n_veh = args.n_vehicles
        soc = args.soc
        max_dec = args.max_decisions

    env_kwargs = {}
    if args.msg_cost is not None:
        env_kwargs["msg_cost"] = float(args.msg_cost)
    if args.byte_cost is not None:
        env_kwargs["byte_cost"] = float(args.byte_cost)
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
        **env_kwargs,
    )
    trainer = MAPPOTrainer(
        env,
        lr=float(args.lr),
        freeze_comm=args.freeze_comm,
        freeze_op=bool(args.freeze_op),
    )
    if args.resume:
        resume_path = project_root() / args.resume
        print(f"resume from {resume_path}", flush=True)
        trainer.load(resume_path)
    before = {k: v.detach().clone() for k, v in trainer.actor.named_parameters()}

    bc_meta = None
    bc_teacher = None
    if args.skip_bc:
        print("skip BC (--skip-bc)", flush=True)
    elif args.bc_native and args.mode == "casablanca":
        bc_teacher = "native_execute"
    elif args.bc_cooperative and args.mode == "casablanca":
        bc_teacher = "cooperative"
    if bc_teacher is not None:
        print(
            f"BC teacher={bc_teacher}: steps={args.bc_steps} epochs={args.bc_epochs}",
            flush=True,
        )
        batch = collect_bc_batch(
            env,
            n_steps=args.bc_steps,
            seed=args.seed + 50,
            teacher=bc_teacher,
            teacher_comm_mode=args.bc_comm_mode,
        )
        losses = behavior_clone(
            trainer.actor, batch, epochs=args.bc_epochs, device=trainer.device
        )
        for r in range(max(0, args.dagger_rounds)):
            # Later DAgger rounds shift to selective so F can prune vs full.
            dagger_comm = args.bc_comm_mode
            if args.bc_comm_mode == "full" and r >= max(1, args.dagger_rounds // 2):
                dagger_comm = "selective"
            batch = dagger_aggregate(
                env,
                trainer.actor,
                n_steps=args.bc_steps // 2,
                seed=args.seed + 200 + r,
                device=trainer.device,
                prior_batch=batch,
                teacher=bc_teacher,
                teacher_comm_mode=dagger_comm,
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
        f"iters={args.iters} steps={args.steps} nv={n_veh} delay={args.delay} "
        f"stage={args.stage} episode_source={getattr(args, 'episode_source', 'n/a')} "
        f"curriculum={getattr(args, 'curriculum', 'n/a')}",
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
        "episode_source": getattr(args, "episode_source", None),
        "curriculum": getattr(args, "curriculum", None),
        "training_protocol": "configs/marl_training_protocol.json",
        "note": (
            "Stage smoke MAPPO on toy scenario."
            if args.mode == "smoke"
            else (
                "Casablanca MAPPO training. Default episode_source=procedural uses "
                "on-the-fly synthetic generator episodes in seed range 10M–20M; "
                "locked_final is never used for training."
            )
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
