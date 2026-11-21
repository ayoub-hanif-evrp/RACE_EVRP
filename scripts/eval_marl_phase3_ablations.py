#!/usr/bin/env python
"""Evaluate teacher / checkpoint on conflict_dense for ablations A/B/C/F."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", default=None, help="Optional MAPPO .pt checkpoint")
    parser.add_argument("--episodes", type=int, default=2)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument(
        "--out",
        default="data/casablanca/online_results/top_tier/phase3_ablation_eval.json",
    )
    args = parser.parse_args()

    from race_casablanca.marl.env import ABLATION_A, ABLATION_B, ABLATION_C, ABLATION_F
    from race_casablanca.marl.phase3_eval import eval_checkpoint, eval_teacher_intent_matched
    from race_casablanca.paths import project_root

    rows = []
    for abl in (ABLATION_A, ABLATION_B, ABLATION_C, ABLATION_F):
        print(f"teacher intent_matched ablation={abl}", flush=True)
        rows.append(
            eval_teacher_intent_matched(
                n_episodes=args.episodes, ablation=abl, master_seed=args.seed
            )
        )
        if args.checkpoint:
            print(f"checkpoint ablation={abl}", flush=True)
            rows.append(
                eval_checkpoint(
                    args.checkpoint,
                    ablation=abl,
                    n_episodes=args.episodes,
                    master_seed=args.seed,
                )
            )

    out = project_root() / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {"rows": rows}
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2), flush=True)
    print(f"wrote {out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
