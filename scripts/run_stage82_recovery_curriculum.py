#!/usr/bin/env python
"""Stage 8.2 recovery curriculum (Priority 3.4).

A. Cooperative BC + DAgger, then MAPPO with communication disabled (A), freeze_comm.
B. Transfer actor → full communication (B); verify messages occur; fine-tune briefly.
C. Transfer → F selective; train communication gate (optionally freeze_op lightly via lower lr).
D. Matched-budget C eval comparison (no claim C is learned).
E. Joint fine-tune F.

Writes stage82_recovery_* artifacts; does not overwrite Stage 8.1.
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


def run(cmd: list[str]) -> None:
    print("+", " ".join(cmd), flush=True)
    subprocess.check_call(cmd)


def eval_ckpt(py: str, ckpt: Path, ablation: str, out_csv: Path, n_vehicles: int, matched_p: float) -> dict:
    from race_casablanca.paths import project_root

    root = project_root()
    cmd = [
        py,
        str(ROOT / "scripts" / "evaluate_race_marl.py"),
        "--checkpoint",
        str(ckpt.relative_to(root)).replace("\\", "/"),
        "--ablation",
        ablation,
        "--n-vehicles",
        str(n_vehicles),
        "--out",
        str(out_csv.relative_to(root)).replace("\\", "/"),
    ]
    run(cmd)
    df = pd.read_csv(out_csv)
    return {
        "mean_ot": float(df["on_time_rate_all"].mean()) if "on_time_rate_all" in df.columns else float("nan"),
        "mean_msgs": float(df["n_bid_messages"].mean()) if "n_bid_messages" in df.columns else float("nan"),
        "mean_bytes": float(df["n_bid_bytes"].mean()) if "n_bid_bytes" in df.columns else float("nan"),
        "n": int(len(df)),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", type=int, nargs="+", default=[0, 1, 2])
    parser.add_argument("--n-vehicles", type=int, default=3)
    parser.add_argument("--bc-steps", type=int, default=384)
    parser.add_argument("--bc-epochs", type=int, default=40)
    parser.add_argument("--dagger-rounds", type=int, default=3)
    parser.add_argument("--phase-a-iters", type=int, default=25)
    parser.add_argument("--phase-b-iters", type=int, default=10)
    parser.add_argument("--phase-c-iters", type=int, default=15)
    parser.add_argument("--phase-e-iters", type=int, default=10)
    parser.add_argument("--steps", type=int, default=48)
    parser.add_argument("--matched-send-p", type=float, default=None)
    parser.add_argument("--python", default=None)
    parser.add_argument("--skip-train", action="store_true")
    args = parser.parse_args()

    from race_casablanca.paths import project_root

    root = project_root()
    py = args.python or str(root / ".venv" / "Scripts" / "python.exe")
    if not Path(py).exists():
        py = sys.executable

    out_dir = root / "data" / "casablanca" / "online_results"
    ckpt_dir = out_dir / "stage82_recovery_checkpoints"
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    t0 = time.time()

    matched_path = out_dir / "stage82_matched_send_p.json"
    if args.matched_send_p is not None:
        matched_p = float(args.matched_send_p)
    elif matched_path.exists():
        matched_p = float(json.loads(matched_path.read_text(encoding="utf-8"))["matched_send_p"])
    else:
        matched_p = 0.30

    rows = []
    for seed in args.seeds:
        stem_a = f"rec_A_no_comm_seed{seed}"
        stem_b = f"rec_B_full_comm_seed{seed}"
        stem_f = f"rec_F_race_marl_seed{seed}"
        stem_c = f"rec_C_random_matched_seed{seed}"
        path_a = ckpt_dir / f"{stem_a}.pt"
        path_b = ckpt_dir / f"{stem_b}.pt"
        path_f = ckpt_dir / f"{stem_f}.pt"
        path_c = ckpt_dir / f"{stem_c}.pt"

        if not args.skip_train:
            # --- Phase A: BC + MAPPO no-comm (freeze_comm) ---
            run(
                [
                    py,
                    str(ROOT / "scripts" / "train_race_marl.py"),
                    "--mode",
                    "casablanca",
                    "--ablation",
                    "A_no_comm",
                    "--seed",
                    str(seed),
                    "--iters",
                    str(args.phase_a_iters),
                    "--steps",
                    str(args.steps),
                    "--n-vehicles",
                    str(args.n_vehicles),
                    "--eval-every",
                    "5",
                    "--bc-cooperative",
                    "--bc-steps",
                    str(args.bc_steps),
                    "--bc-epochs",
                    str(args.bc_epochs),
                    "--dagger-rounds",
                    str(args.dagger_rounds),
                    "--freeze-comm",
                    "--matched-send-p",
                    str(matched_p),
                    "--stage",
                    "8.2_recovery_A",
                    "--out",
                    str(path_a.relative_to(root)).replace("\\", "/"),
                ]
            )

            # --- Phase B: continue from A into full-comm ---
            # train_race_marl doesn't have --init-checkpoint yet; add via inline continue
            run(
                [
                    py,
                    "-c",
                    f"""
import sys
from pathlib import Path
sys.path.insert(0, r'{root / "src"}')
from race_casablanca.marl.env import RaceMultiAgentEnv
from race_casablanca.marl.mappo import MAPPOTrainer
from race_casablanca.marl.scenarios import load_casablanca_pool, make_pool_factory
from race_casablanca.paths import project_root
import json, torch

pool = load_casablanca_pool(split='train')
factory = make_pool_factory(pool, n_vehicles={args.n_vehicles}, procedural_jitter=True)
env = RaceMultiAgentEnv(scenario_factory=factory, n_vehicles={args.n_vehicles}, ablation='B_full_comm', seed={seed}, max_decisions=400, matched_send_p={matched_p})
tr = MAPPOTrainer(env)
tr.load(Path(r'{path_a}'))
best = {{'ot': -1.0, 'path': None}}
out = Path(r'{path_b}')
def on_eval(i, ev, m):
    if ev['mean_ot'] >= best['ot']:
        best['ot'] = float(ev['mean_ot'])
        best['path'] = out.with_name(out.stem + '_best.pt')
        tr.save(best['path'])
tr.train(iterations={args.phase_b_iters}, steps_per_iter={args.steps}, eval_every=5, eval_episodes=2, on_eval=on_eval)
tr.save(out)
ev = tr.evaluate_deterministic(2)
meta = {{'phase': 'B', 'seed': {seed}, 'eval': ev, 'init': r'{path_a}', 'best': str(best['path']) if best['path'] else None}}
out.with_suffix('.json').write_text(json.dumps(meta, indent=2), encoding='utf-8')
print('PHASE_B', meta)
""",
                ]
            )

            # --- Phase C+E: F selective from B, then joint ---
            run(
                [
                    py,
                    "-c",
                    f"""
import sys
from pathlib import Path
sys.path.insert(0, r'{root / "src"}')
from race_casablanca.marl.env import RaceMultiAgentEnv
from race_casablanca.marl.mappo import MAPPOTrainer
from race_casablanca.marl.scenarios import load_casablanca_pool, make_pool_factory
import json

pool = load_casablanca_pool(split='train')
factory = make_pool_factory(pool, n_vehicles={args.n_vehicles}, procedural_jitter=True)
env = RaceMultiAgentEnv(scenario_factory=factory, n_vehicles={args.n_vehicles}, ablation='F_race_marl', seed={seed}, max_decisions=400, matched_send_p={matched_p})
tr = MAPPOTrainer(env)
tr.load(Path(r'{path_b}'))
# Phase C: train selective gate (comm active)
best = {{'ot': -1.0, 'path': None}}
out = Path(r'{path_f}')
def on_eval(i, ev, m):
    if ev['mean_ot'] >= best['ot']:
        best['ot'] = float(ev['mean_ot'])
        best['path'] = out.with_name(out.stem + '_best.pt')
        tr.save(best['path'])
tr.train(iterations={args.phase_c_iters}, steps_per_iter={args.steps}, eval_every=5, eval_episodes=2, on_eval=on_eval)
# Phase E: joint fine-tune a bit more
tr.train(iterations={args.phase_e_iters}, steps_per_iter={args.steps}, eval_every=5, eval_episodes=2, on_eval=on_eval)
tr.save(out)
ev = tr.evaluate_deterministic(2)
meta = {{'phase': 'C+E', 'seed': {seed}, 'eval': ev, 'init': r'{path_b}', 'best': str(best['path']) if best['path'] else None}}
out.with_suffix('.json').write_text(json.dumps(meta, indent=2), encoding='utf-8')
print('PHASE_CE', meta)
""",
                ]
            )

            # --- Phase D control: C random matched from same A init (routing-matched) ---
            run(
                [
                    py,
                    "-c",
                    f"""
import sys
from pathlib import Path
sys.path.insert(0, r'{root / "src"}')
from race_casablanca.marl.env import RaceMultiAgentEnv
from race_casablanca.marl.mappo import MAPPOTrainer
from race_casablanca.marl.scenarios import load_casablanca_pool, make_pool_factory
import json

pool = load_casablanca_pool(split='train')
factory = make_pool_factory(pool, n_vehicles={args.n_vehicles}, procedural_jitter=True)
env = RaceMultiAgentEnv(scenario_factory=factory, n_vehicles={args.n_vehicles}, ablation='C_random_matched', seed={seed}, max_decisions=400, matched_send_p={matched_p})
tr = MAPPOTrainer(env)
tr.load(Path(r'{path_a}'))
out = Path(r'{path_c}')
tr.train(iterations={args.phase_c_iters + args.phase_e_iters}, steps_per_iter={args.steps}, eval_every=5, eval_episodes=2)
tr.save(out)
ev = tr.evaluate_deterministic(2)
meta = {{'phase': 'D_control', 'seed': {seed}, 'eval': ev, 'matched_send_p': {matched_p}}}
out.with_suffix('.json').write_text(json.dumps(meta, indent=2), encoding='utf-8')
print('PHASE_D', meta)
""",
                ]
            )

        # Evaluate best available checkpoints
        for label, abl, path in [
            ("A", "A_no_comm", path_a),
            ("B", "B_full_comm", path_b),
            ("F", "F_race_marl", path_f),
            ("C", "C_random_matched", path_c),
        ]:
            best = path.with_name(path.stem + "_best.pt")
            ckpt = best if best.exists() else path
            if not ckpt.exists():
                continue
            out_csv = out_dir / f"stage82_recovery_eval_{abl}_seed{seed}.csv"
            stats = eval_ckpt(py, ckpt, abl, out_csv, args.n_vehicles, matched_p)
            rows.append({"phase": label, "ablation": abl, "seed": seed, **stats, "checkpoint": str(ckpt)})

    summary = {
        "stage": "8.2_recovery",
        "matched_send_p": matched_p,
        "seeds": list(args.seeds),
        "wall_time_s": round(time.time() - t0, 2),
        "rows": rows,
    }
    if rows:
        rdf = pd.DataFrame(rows)
        rdf.to_csv(out_dir / "stage82_recovery_eval.csv", index=False)
        summary["by_phase"] = (
            rdf.groupby("phase")["mean_ot"].agg(["mean", "std", "count"]).reset_index().to_dict(orient="records")
        )
    (out_dir / "stage82_recovery_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
