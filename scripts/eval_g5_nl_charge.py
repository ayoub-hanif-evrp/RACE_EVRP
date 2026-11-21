#!/usr/bin/env python
"""G5: partial NL charge (0.70) vs always-full (1.0) on energy-binding conflict."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", default="0,1,2")
    parser.add_argument("--episodes", type=int, default=4)
    parser.add_argument("--n-vehicles", type=int, default=3)
    parser.add_argument("--regime", default="conflict_dense")
    parser.add_argument("--comm-mode", default="full")
    parser.add_argument(
        "--out",
        default="data/casablanca/online_results/top_tier/phase4/g5_nl_charge.json",
    )
    args = parser.parse_args()

    from race_casablanca.marl.g5_nl_charge import (
        exact_partial_beats_full,
        g5_binding_rows,
        nl_taper_costs,
        summarize_g5,
    )
    from race_casablanca.paths import project_root

    seeds = [int(s.strip()) for s in str(args.seeds).split(",") if s.strip()]
    exact = exact_partial_beats_full()
    taper = nl_taper_costs()
    print(
        f"NL taper from {taper['soc_from']:.2f}: "
        f"to-0.70 {taper['partial_to_0_70_s']/60:.1f}min, "
        f"to-1.0 {taper['full_to_1_00_s']/60:.1f}min "
        f"({taper['full_over_partial']:.2f}x)",
        flush=True,
    )
    print(
        f"exact {exact['instance']}: best={exact['best_on_time']} "
        f"always_full={exact['always_full_on_time']} pass={exact['pass']}",
        flush=True,
    )

    per_seed = []
    for seed in seeds:
        print(f"=== master_seed={seed} ===", flush=True)
        rows = g5_binding_rows(
            n_episodes=args.episodes,
            master_seed=seed,
            n_vehicles=args.n_vehicles,
            regime=args.regime,
            comm_mode=args.comm_mode,
        )
        summary = summarize_g5(rows, exact=exact, taper=taper)
        print(
            f"  partial_ot={summary['mean_partial_ot']:.3f} "
            f"full_ot={summary['mean_full_ot']:.3f} "
            f"delta={summary['mean_delta_ot']:+.3f} "
            f"charge_s partial/full="
            f"{summary['mean_partial_charge_s']:.0f}/{summary['mean_full_charge_s']:.0f} "
            f"hard={summary['hard_pass']} soft={summary['soft_pass']}",
            flush=True,
        )
        per_seed.append({"master_seed": seed, "summary": summary, "episodes": rows})

    n_hard = sum(1 for s in per_seed if s["summary"]["hard_pass"])
    n_soft = sum(1 for s in per_seed if s["summary"]["soft_pass"])
    mean_delta = sum(s["summary"]["mean_delta_ot"] for s in per_seed) / max(1, len(per_seed))
    agg = {
        "gate": "G5",
        "n_seeds": len(per_seed),
        "n_hard_pass": n_hard,
        "n_soft_pass": n_soft,
        "mean_delta_ot": mean_delta,
        "exact": exact,
        "nl_taper": taper,
        "aggregate_hard_pass": bool(n_hard >= max(1, len(seeds) - 1) and exact["pass"]),
        "aggregate_soft_pass": bool(n_soft >= max(1, len(seeds) - 1) and exact["pass"]),
    }
    payload = {
        "regime": args.regime,
        "energy_binding": True,
        "partial_soc": 0.70,
        "full_soc": 1.00,
        "comm_mode": args.comm_mode,
        "episodes_per_seed": args.episodes,
        "summary": agg,
        "seeds": per_seed,
    }
    out = project_root() / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(agg, indent=2), flush=True)
    print(f"wrote {out}", flush=True)
    return 0 if agg["aggregate_hard_pass"] or agg["aggregate_soft_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
