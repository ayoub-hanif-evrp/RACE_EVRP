#!/usr/bin/env python
"""Smoke-check procedural MARL episode capacity (no training, no locked_final)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--n", type=int, default=12, help="Episodes to materialize in memory")
    p.add_argument("--master-seed", type=int, default=0)
    args = p.parse_args()

    from race_casablanca.marl.episode_sampler import make_procedural_train_factory
    from race_casablanca.marl.seed_banks import FORBIDDEN_TRAIN_SEEDS, TRAIN_SEED_RANGE

    gen, factory = make_procedural_train_factory(
        master_seed=args.master_seed, n_vehicles=3, load_network=False
    )
    rows = []
    for i in range(args.n):
        sc = factory(seed=i)
        meta = sc["metadata"]
        seed = int(meta["seed"])
        assert seed not in FORBIDDEN_TRAIN_SEEDS
        assert TRAIN_SEED_RANGE[0] <= seed <= TRAIN_SEED_RANGE[1]
        rows.append(
            {
                "episode": i,
                "regime": meta["regime"],
                "seed": seed,
                "n_requests": meta["n_requests"],
                "scenario_id": sc["scenario_id"],
            }
        )
    summary = {
        "n_episodes": len(rows),
        "unique_seeds": len({r["seed"] for r in rows}),
        "regimes": sorted({r["regime"] for r in rows}),
        "mean_requests": sum(r["n_requests"] for r in rows) / max(1, len(rows)),
        "train_seed_range": list(TRAIN_SEED_RANGE),
        "locked_final_used": False,
        "claim": gen.config.get("generator_version"),
        "episodes": rows,
    }
    print(json.dumps(summary, indent=2))
    print("PASS procedural training stream smoke", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
