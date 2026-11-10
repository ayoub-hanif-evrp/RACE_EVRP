#!/usr/bin/env python
"""Run Milestone 3–4 compact Casablanca MAPPO train + ablations + eval."""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def run(cmd: list[str]) -> None:
    print("+", " ".join(cmd), flush=True)
    subprocess.check_call(cmd)


def main() -> int:
    from race_casablanca.paths import project_root

    py = sys.executable
    t0 = time.time()

    # Milestone 3: primary F across two seeds (validation-selected checkpoints)
    for seed in (0, 1):
        out = f"data/casablanca/online_results/marl_checkpoints/casablanca_F_race_marl_seed{seed}.pt"
        run(
            [
                py,
                str(ROOT / "scripts" / "train_race_marl.py"),
                "--mode",
                "casablanca",
                "--ablation",
                "F_race_marl",
                "--seed",
                str(seed),
                "--iters",
                "40",
                "--steps",
                "48",
                "--n-vehicles",
                "3",
                "--eval-every",
                "5",
                "--out",
                out,
            ]
        )
        best = (
            project_root()
            / f"data/casablanca/online_results/marl_checkpoints/casablanca_F_race_marl_seed{seed}_best.pt"
        )
        ckpt = (
            str(best.relative_to(project_root())).replace("\\", "/")
            if best.exists()
            else out
        )
        run(
            [
                py,
                str(ROOT / "scripts" / "evaluate_race_marl.py"),
                "--checkpoint",
                ckpt,
                "--ablation",
                "F_race_marl",
                "--out",
                f"data/casablanca/online_results/marl_eval_F_seed{seed}.csv",
            ]
        )

    # Milestone 4: train A–E (matched budget), then eval A–F + scalability
    run(
        [
            py,
            str(ROOT / "scripts" / "run_race_marl_ablations.py"),
            "--iters",
            "30",
            "--steps",
            "48",
            "--seeds",
            "0",
            "--n-vehicles",
            "3",
            "--ablations",
            "A_no_comm",
            "B_full_comm",
            "C_random_matched",
            "D_selective",
            "E_selective_no_energy",
            "--skip-scale",
            "--python",
            py,
        ]
    )
    run(
        [
            py,
            str(ROOT / "scripts" / "run_race_marl_ablations.py"),
            "--seeds",
            "0",
            "--n-vehicles",
            "3",
            "--ablations",
            "A_no_comm",
            "B_full_comm",
            "C_random_matched",
            "D_selective",
            "E_selective_no_energy",
            "F_race_marl",
            "--skip-train",
            "--python",
            py,
        ]
    )

    summary = {
        "wall_time_s": round(time.time() - t0, 2),
        "milestone3": "F_race_marl seeds 0/1, 40 iters, Casablanca train pool",
        "milestone4": "A–E seed0 30 iters + A–F eval + frozen-F scalability transfer",
    }
    out = project_root() / "data/casablanca/online_results/marl_milestone34_summary.json"
    out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
