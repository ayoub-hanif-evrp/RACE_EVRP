#!/usr/bin/env python
"""Phase 3 / Gate G2: BC(+DAgger) OT on conflict_dense vs teacher ceiling."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bc-steps", type=int, default=256)
    parser.add_argument("--bc-epochs", type=int, default=25)
    parser.add_argument("--dagger-rounds", type=int, default=1)
    parser.add_argument("--episodes", type=int, default=4)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--max-decisions", type=int, default=2000)
    parser.add_argument(
        "--regime",
        default="baseline",
        choices=["baseline", "peak_stress", "tight_windows", "conflict_dense"],
        help="Procedural regime for G2 (baseline for absolute ≥0.78)",
    )
    parser.add_argument(
        "--energy-binding",
        action="store_true",
        help="Low-SOC stress (use relative G2 vs teacher; absolute 0.78 unlikely)",
    )
    parser.add_argument("--skip-teacher", action="store_true")
    parser.add_argument(
        "--out",
        default="data/casablanca/online_results/top_tier/phase3_g2_bc_eval.json",
    )
    args = parser.parse_args()

    from race_casablanca.marl.phase3_eval import eval_bc_g2, eval_teacher_execute_ceiling
    from race_casablanca.paths import project_root

    payload: dict = {
        "seed": args.seed,
        "episodes": args.episodes,
        "regime": args.regime,
        "energy_binding": bool(args.energy_binding),
    }
    teacher_ot = None
    if not args.skip_teacher:
        print(
            f"teacher ceiling regime={args.regime} energy_binding={args.energy_binding}...",
            flush=True,
        )
        payload["teacher"] = eval_teacher_execute_ceiling(
            n_episodes=args.episodes,
            master_seed=args.seed,
            max_decisions=args.max_decisions,
            energy_binding=bool(args.energy_binding),
            regime=args.regime,
        )
        teacher_ot = float(payload["teacher"]["mean_ot"])
        print(f"  teacher mean_ot={teacher_ot:.3f}", flush=True)

    print(
        f"BC G2: regime={args.regime} steps={args.bc_steps} epochs={args.bc_epochs} "
        f"dagger={args.dagger_rounds} eval_eps={args.episodes} "
        f"energy_binding={args.energy_binding}",
        flush=True,
    )
    payload["bc"] = eval_bc_g2(
        bc_steps=args.bc_steps,
        bc_epochs=args.bc_epochs,
        dagger_rounds=args.dagger_rounds,
        n_eval_episodes=args.episodes,
        master_seed=args.seed,
        max_decisions=args.max_decisions,
        energy_binding=bool(args.energy_binding),
        regime=args.regime,
        teacher_mean_ot=teacher_ot,
    )
    print(
        f"  BC mean_ot={payload['bc']['mean_ot']:.3f} "
        f"g2_pass={payload['bc']['g2_pass']} "
        f"abs={payload['bc']['g2_absolute_pass']} "
        f"rel={payload['bc']['g2_relative_pass']} "
        f"gap={payload['bc']['ot_gap_vs_teacher']} "
        f"bc_acc={payload['bc']['bc']}",
        flush=True,
    )

    out = project_root() / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"wrote {out}", flush=True)
    return 0 if payload["bc"]["g2_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
