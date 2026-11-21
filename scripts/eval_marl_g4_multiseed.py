#!/usr/bin/env python
"""Multi-seed G4 confirmation: A/B/C/F on conflict_dense."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def _g4_criteria(a: float, b: float, f: float, bytes_f: float, bytes_b: float) -> dict:
    gap_a = f - a
    gap_b = f - b
    br = bytes_f / max(1.0, bytes_b)
    return {
        "F_minus_A": gap_a,
        "F_minus_B": gap_b,
        "bytes_F_over_B": br,
        "hard_pass": bool(gap_a >= 0.03 and gap_b >= -0.03 and br <= 0.7),
        "soft_pass": bool(gap_a > 0.0 and gap_b >= -0.05 and br < 1.0),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--checkpoint",
        default="data/casablanca/online_results/top_tier/marl_checkpoints/phase3_F_conflict_g4mask_seed0_best.pt",
    )
    parser.add_argument("--episodes", type=int, default=4)
    parser.add_argument("--seeds", default="0,1,2")
    parser.add_argument(
        "--out",
        default="data/casablanca/online_results/top_tier/phase3_g4_multiseed.json",
    )
    args = parser.parse_args()

    from race_casablanca.marl.env import ABLATION_A, ABLATION_B, ABLATION_C, ABLATION_F
    from race_casablanca.marl.phase3_eval import eval_checkpoint
    from race_casablanca.paths import project_root

    seeds = [int(s.strip()) for s in str(args.seeds).split(",") if s.strip()]
    ablations = (ABLATION_A, ABLATION_B, ABLATION_C, ABLATION_F)
    per_seed = []
    for seed in seeds:
        print(f"=== master_seed={seed} ===", flush=True)
        rows = {}
        for abl in ablations:
            r = eval_checkpoint(
                args.checkpoint,
                ablation=abl,
                n_episodes=args.episodes,
                master_seed=seed,
                regime="conflict_dense",
            )
            msgs = sum(e["n_bid_messages"] for e in r["episodes"]) / max(1, len(r["episodes"]))
            rows[abl] = {
                "mean_ot": float(r["mean_ot"]),
                "mean_bytes": float(r["mean_bytes"]),
                "mean_msgs": float(msgs),
            }
            print(
                f"  {abl}: ot={r['mean_ot']:.3f} bytes={r['mean_bytes']:.0f} msgs={msgs:.1f}",
                flush=True,
            )
        crit = _g4_criteria(
            rows[ABLATION_A]["mean_ot"],
            rows[ABLATION_B]["mean_ot"],
            rows[ABLATION_F]["mean_ot"],
            rows[ABLATION_F]["mean_bytes"],
            rows[ABLATION_B]["mean_bytes"],
        )
        print(f"  G4 {crit}", flush=True)
        per_seed.append({"master_seed": seed, "rows": rows, "criteria": crit})

    n_hard = sum(1 for s in per_seed if s["criteria"]["hard_pass"])
    n_soft = sum(1 for s in per_seed if s["criteria"]["soft_pass"])
    mean_gap_a = sum(s["criteria"]["F_minus_A"] for s in per_seed) / len(per_seed)
    mean_gap_b = sum(s["criteria"]["F_minus_B"] for s in per_seed) / len(per_seed)
    mean_br = sum(s["criteria"]["bytes_F_over_B"] for s in per_seed) / len(per_seed)
    summary = {
        "n_seeds": len(per_seed),
        "n_hard_pass": n_hard,
        "n_soft_pass": n_soft,
        "mean_F_minus_A": mean_gap_a,
        "mean_F_minus_B": mean_gap_b,
        "mean_bytes_F_over_B": mean_br,
        "aggregate_hard_pass": bool(
            mean_gap_a >= 0.03 and mean_gap_b >= -0.03 and mean_br <= 0.7
        ),
    }
    payload = {
        "checkpoint": args.checkpoint,
        "episodes_per_seed": args.episodes,
        "summary": summary,
        "seeds": per_seed,
    }
    out = project_root() / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)
    print(f"wrote {out}", flush=True)
    return 0 if summary["aggregate_hard_pass"] or n_hard >= max(1, len(seeds) - 1) else 2


if __name__ == "__main__":
    raise SystemExit(main())
