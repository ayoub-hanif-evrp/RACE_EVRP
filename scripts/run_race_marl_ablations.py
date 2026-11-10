#!/usr/bin/env python
"""Milestone 4: train/eval learned communication ablations A–F + compact scalability.

Compact primary matrix (not full combinatorial grid):
  fleets {3,5}, workloads via existing regimes, delay {0,30}, loss {0,0.1}
  on the best F checkpoint where retraining is not required.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

ABLATIONS = [
    "A_no_comm",
    "B_full_comm",
    "C_random_matched",
    "D_selective",
    "E_selective_no_energy",
    "F_race_marl",
]


def run(cmd: list[str]) -> None:
    print("+", " ".join(cmd), flush=True)
    subprocess.check_call(cmd)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iters", type=int, default=25)
    parser.add_argument("--steps", type=int, default=48)
    parser.add_argument("--seeds", type=int, nargs="+", default=[0])
    parser.add_argument("--n-vehicles", type=int, default=3)
    parser.add_argument("--skip-train", action="store_true")
    parser.add_argument(
        "--ablations",
        nargs="+",
        default=ABLATIONS,
        help="Subset of ablation ids to train/eval",
    )
    parser.add_argument("--skip-scale", action="store_true")
    parser.add_argument("--python", default=sys.executable)
    args = parser.parse_args()
    selected = list(args.ablations)

    from race_casablanca.paths import project_root

    py = args.python
    ckpt_dir = project_root() / "data" / "casablanca" / "online_results" / "marl_checkpoints"
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    results_dir = project_root() / "data" / "casablanca" / "online_results"
    t0 = time.time()

    train_rows = []
    if not args.skip_train:
        for abl in selected:
            for seed in args.seeds:
                stem = f"casablanca_{abl}_seed{seed}"
                out = ckpt_dir / f"{stem}.pt"
                cmd = [
                    py,
                    str(ROOT / "scripts" / "train_race_marl.py"),
                    "--mode",
                    "casablanca",
                    "--ablation",
                    abl,
                    "--seed",
                    str(seed),
                    "--iters",
                    str(args.iters),
                    "--steps",
                    str(args.steps),
                    "--n-vehicles",
                    str(args.n_vehicles),
                    "--eval-every",
                    "5",
                    "--out",
                    str(out.relative_to(project_root())).replace("\\", "/"),
                ]
                run(cmd)
                meta_path = out.with_suffix(".json")
                meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
                train_rows.append(
                    {
                        "ablation": abl,
                        "seed": seed,
                        "mean_ot": (meta.get("eval") or {}).get("mean_ot"),
                        "mean_return": (meta.get("eval") or {}).get("mean_return"),
                        "wall_time_s": meta.get("wall_time_s"),
                        "n_updates": meta.get("n_updates"),
                        "params_changed": meta.get("params_changed"),
                        "checkpoint": str(out).replace("\\", "/"),
                        "best_checkpoint": meta.get("best_checkpoint"),
                    }
                )

    # Evaluate each trained ablation on shared diagnostic set
    eval_rows = []
    for abl in selected:
        for seed in args.seeds:
            stem = f"casablanca_{abl}_seed{seed}"
            best = ckpt_dir / f"{stem}_best.pt"
            ckpt = best if best.exists() else ckpt_dir / f"{stem}.pt"
            if not ckpt.exists():
                print(f"SKIP eval missing {ckpt}", flush=True)
                continue
            out_csv = results_dir / f"marl_eval_{abl}_seed{seed}.csv"
            cmd = [
                py,
                str(ROOT / "scripts" / "evaluate_race_marl.py"),
                "--checkpoint",
                str(ckpt.relative_to(project_root())).replace("\\", "/"),
                "--ablation",
                abl,
                "--n-vehicles",
                str(args.n_vehicles),
                "--out",
                str(out_csv.relative_to(project_root())).replace("\\", "/"),
            ]
            run(cmd)
            df = pd.read_csv(out_csv)
            eval_rows.append(
                {
                    "ablation": abl,
                    "seed": seed,
                    "mean_ot": float(df["on_time_rate_all"].mean()),
                    "mean_served": float(df["n_served"].mean()),
                    "mean_sends": float(df["n_send_actions"].mean()),
                    "n_scenarios": len(df),
                    "checkpoint": str(ckpt).replace("\\", "/"),
                }
            )

    # Compact scalability using best available F checkpoint (prefer seed1_best)
    scale_rows = []
    f_candidates = [
        ckpt_dir / "casablanca_F_race_marl_seed1_best.pt",
        ckpt_dir / "casablanca_F_race_marl_seed1.pt",
        ckpt_dir / "casablanca_F_race_marl_seed0_best.pt",
        ckpt_dir / "casablanca_F_race_marl_seed0.pt",
    ]
    f_ckpt = next((p for p in f_candidates if p.exists()), None)
    if f_ckpt is not None and not args.skip_scale:
        for nv in (3, 5):
            for delay in (0.0, 30.0):
                for loss in (0.0, 0.1):
                    if nv == 5 and delay == 30.0 and loss == 0.1:
                        continue  # keep matrix compact
                    out_csv = results_dir / f"marl_scale_nv{nv}_d{int(delay)}_loss{int(loss*100)}.csv"
                    cmd = [
                        py,
                        str(ROOT / "scripts" / "evaluate_race_marl.py"),
                        "--checkpoint",
                        str(f_ckpt.relative_to(project_root())).replace("\\", "/"),
                        "--ablation",
                        "F_race_marl",
                        "--n-vehicles",
                        str(nv),
                        "--delay",
                        str(delay),
                        "--packet-loss",
                        str(loss),
                        "--out",
                        str(out_csv.relative_to(project_root())).replace("\\", "/"),
                    ]
                    run(cmd)
                    df = pd.read_csv(out_csv)
                    scale_rows.append(
                        {
                            "n_vehicles": nv,
                            "delay_s": delay,
                            "packet_loss_p": loss,
                            "mean_ot": float(df["on_time_rate_all"].mean()),
                            "mean_served": float(df["n_served"].mean()),
                            "mean_sends": float(df["n_send_actions"].mean()),
                            "n_scenarios": len(df),
                        }
                    )

    summary = {
        "wall_time_s": round(time.time() - t0, 2),
        "train": train_rows,
        "eval": eval_rows,
        "scalability": scale_rows,
        "iters": args.iters,
        "steps": args.steps,
        "seeds": args.seeds,
        "note": (
            "Learned ablations A–F with matched MAPPO budget; "
            "scalability is frozen-F transfer eval (not re-trained per cell)."
        ),
    }
    out_json = results_dir / "marl_ablations_summary.json"
    out_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    if train_rows:
        pd.DataFrame(train_rows).to_csv(results_dir / "marl_ablations_train.csv", index=False)
    if eval_rows:
        pd.DataFrame(eval_rows).to_csv(results_dir / "marl_ablations_eval.csv", index=False)
    if scale_rows:
        pd.DataFrame(scale_rows).to_csv(results_dir / "marl_scalability.csv", index=False)
    print(json.dumps(summary, indent=2), flush=True)
    print(f"Wrote {out_json}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
