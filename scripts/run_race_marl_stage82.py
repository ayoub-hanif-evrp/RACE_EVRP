#!/usr/bin/env python
"""Stage 8.2: causal coordination repair, cooperative BC recovery, multi-seed fair matrix.

Does NOT overwrite Stage 8.1 artifacts. Writes under online_results/stage82_*.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from copy import deepcopy
from pathlib import Path

import numpy as np
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


def calibrate_matched_send_p(n_vehicles: int = 3, n_episodes: int = 3) -> float:
    """Predeclare random-matched budget from selective cooperative teacher send rate."""
    from race_casablanca.marl.bc import CooperativeTeacherAdapter, cooperative_teacher_actions
    from race_casablanca.marl.env import ABLATION_D, RaceMultiAgentEnv
    from race_casablanca.marl.scenarios import load_casablanca_pool, make_pool_factory

    pool = load_casablanca_pool(split="train")
    factory = make_pool_factory(pool, n_vehicles=n_vehicles, procedural_jitter=True)
    env = RaceMultiAgentEnv(
        scenario_factory=factory,
        n_vehicles=n_vehicles,
        ablation=ABLATION_D,
        seed=0,
        max_decisions=200,
    )
    adapter = CooperativeTeacherAdapter()
    sends = 0
    opps = 0
    for ep in range(n_episodes):
        adapter.reset()
        steps = env.reset(seed=100 + ep)
        done = False
        while not done:
            labels = cooperative_teacher_actions(env, adapter)
            for vid, (op, comm) in labels.items():
                opps += 1
                if comm < 5:
                    sends += 1
            steps = env.step(labels)
            done = list(steps.values())[0].done
    p = float(sends) / max(1, opps)
    # Clamp to a stable predeclared band
    p = float(np.clip(p, 0.15, 0.85))
    return p


def eval_nonlearning(n_vehicles: int, delay: float, out_csv: Path) -> pd.DataFrame:
    from race_casablanca.marl.scenarios import resolve_eval_dirs
    from race_casablanca.paths import project_root
    from race_casablanca.policies import ChargingController, GreedyInsertionPolicy, RaceCooperativePolicy
    from race_casablanca.sim.environment import OnlineSimulator, SimConfig
    from race_casablanca.sim.scenario_loader import load_congestion_model, load_drive_graph, load_scenario
    from race_casablanca.sim.types import RequestStatus

    graph = load_drive_graph()
    model = load_congestion_model()
    paths = resolve_eval_dirs()
    modes = [
        ("nl_none", "none"),
        ("nl_full", "full"),
        ("nl_selective", "selective"),
        ("greedy_charge70", None),
    ]
    rows = []
    for path in paths:
        sc = load_scenario(path, load_network=False, graph=graph, model=model)
        for label, mode in modes:
            reqs = deepcopy(sc.requests)
            for r in reqs:
                r.status = RequestStatus.UNRELEASED
                r.owner = None
            if mode is None:
                pol = GreedyInsertionPolicy(
                    charging=ChargingController(mode="charge_to_target", target_soc=0.70)
                )
            else:
                pol = RaceCooperativePolicy(
                    comm_mode=mode, enable_readiness_charge=True, rng_seed=7
                )
            sim = OnlineSimulator(
                scenario_id=f"{sc.scenario_id}/{label}",
                graph=graph,
                model=model,
                requests=reqs,
                fleet={**sc.fleet, "n_vehicles": n_vehicles},
                depot_node=sc.depot_node,
                shift_start_s=sc.shift_start_s,
                shift_end_s=sc.shift_end_s,
                config=SimConfig(
                    info_mode="restricted",
                    seed=0,
                    initial_soc=0.35,
                    n_vehicles=n_vehicles,
                    message_delay_s=delay,
                    packet_loss_p=0.0,
                    periodic_state_broadcast=False,
                    decision_on_release=True,
                    day=str(getattr(sc, "day", "Monday")),
                ),
                policy=pol,
            )
            m = sim.run().to_dict()
            rows.append(
                {
                    "method": label,
                    "scenario": path.name,
                    "on_time_rate_all": m.get("on_time_rate_all"),
                    "n_served": m.get("n_served"),
                    "n_completed": m.get("n_served"),
                    "n_bid_messages": m.get("n_bid_messages"),
                    "n_bid_bytes": m.get("n_bid_bytes"),
                    "delay_s": delay,
                }
            )
    df = pd.DataFrame(rows)
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_csv, index=False)
    return df


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iters", type=int, default=20)
    parser.add_argument("--steps", type=int, default=48)
    parser.add_argument("--bc-steps", type=int, default=256)
    parser.add_argument("--bc-epochs", type=int, default=30)
    parser.add_argument("--seeds", type=int, nargs="+", default=[0, 1, 2])
    parser.add_argument("--n-vehicles", type=int, default=3)
    parser.add_argument("--skip-train", action="store_true")
    parser.add_argument("--skip-nl", action="store_true")
    parser.add_argument("--ablations", nargs="+", default=ABLATIONS)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--matched-send-p", type=float, default=None)
    args = parser.parse_args()

    from race_casablanca.paths import project_root

    root = project_root()
    out_dir = root / "data" / "casablanca" / "online_results"
    ckpt_dir = out_dir / "stage82_checkpoints"
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    t0 = time.time()

    if args.matched_send_p is None:
        print("Calibrating matched_send_p from cooperative selective teacher...", flush=True)
        matched_p = calibrate_matched_send_p(n_vehicles=args.n_vehicles)
    else:
        matched_p = float(args.matched_send_p)
    print(f"matched_send_p (predeclared) = {matched_p:.4f}", flush=True)
    (out_dir / "stage82_matched_send_p.json").write_text(
        json.dumps({"matched_send_p": matched_p, "source": "cooperative_selective_teacher"}, indent=2),
        encoding="utf-8",
    )

    nl_csv = out_dir / "stage82_nonlearning_eval.csv"
    if not args.skip_nl:
        print("Evaluating non-learning baselines...", flush=True)
        eval_nonlearning(args.n_vehicles, 0.0, nl_csv)

    train_rows = []
    if not args.skip_train:
        for abl in args.ablations:
            for seed in args.seeds:
                stem = f"stage82_{abl}_seed{seed}"
                out = ckpt_dir / f"{stem}.pt"
                cmd = [
                    args.python,
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
                    "--bc-cooperative",
                    "--bc-steps",
                    str(args.bc_steps),
                    "--bc-epochs",
                    str(args.bc_epochs),
                    "--matched-send-p",
                    str(matched_p),
                    "--stage",
                    "8.2",
                    "--out",
                    str(out.relative_to(root)).replace("\\", "/"),
                ]
                run(cmd)
                meta = json.loads(out.with_suffix(".json").read_text(encoding="utf-8"))
                train_rows.append(
                    {
                        "ablation": abl,
                        "seed": seed,
                        "mean_ot": (meta.get("eval") or {}).get("mean_ot"),
                        "bc_op_acc": (meta.get("bc") or {}).get("op_accuracy"),
                        "bc_comm_acc": (meta.get("bc") or {}).get("comm_accuracy"),
                        "wall_time_s": meta.get("wall_time_s"),
                        "checkpoint": str(out),
                        "best_checkpoint": meta.get("best_checkpoint"),
                    }
                )

    # Evaluate learned checkpoints on validation set
    eval_rows = []
    for abl in args.ablations:
        for seed in args.seeds:
            stem = f"stage82_{abl}_seed{seed}"
            best = ckpt_dir / f"{stem}_best.pt"
            ckpt = best if best.exists() else ckpt_dir / f"{stem}.pt"
            if not ckpt.exists():
                continue
            out_csv = out_dir / f"stage82_eval_{abl}_seed{seed}.csv"
            cmd = [
                args.python,
                str(ROOT / "scripts" / "evaluate_race_marl.py"),
                "--checkpoint",
                str(ckpt.relative_to(root)).replace("\\", "/"),
                "--ablation",
                abl,
                "--n-vehicles",
                str(args.n_vehicles),
                "--out",
                str(out_csv.relative_to(root)).replace("\\", "/"),
            ]
            run(cmd)
            df = pd.read_csv(out_csv)
            df["ablation"] = abl
            df["seed"] = seed
            eval_rows.append(df)

    summary = {
        "stage": "8.2",
        "matched_send_p": matched_p,
        "seeds": list(args.seeds),
        "iters": args.iters,
        "wall_time_s": round(time.time() - t0, 2),
        "train": train_rows,
    }
    if eval_rows:
        edf = pd.concat(eval_rows, ignore_index=True)
        edf.to_csv(out_dir / "stage82_learned_eval.csv", index=False)
        # Multi-seed means
        if "on_time_rate_all" in edf.columns:
            g = edf.groupby(["ablation", "seed"], as_index=False)["on_time_rate_all"].mean()
            g2 = g.groupby("ablation")["on_time_rate_all"].agg(["mean", "std", "count"])
            summary["learned_ot_by_ablation"] = g2.reset_index().to_dict(orient="records")
            g.to_csv(out_dir / "stage82_learned_ot_by_seed.csv", index=False)
    if nl_csv.exists():
        ndf = pd.read_csv(nl_csv)
        summary["nl_ot_by_method"] = (
            ndf.groupby("method")["on_time_rate_all"].mean().to_dict()
        )
    (out_dir / "stage82_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    if train_rows:
        pd.DataFrame(train_rows).to_csv(out_dir / "stage82_train.csv", index=False)
    print(json.dumps(summary, indent=2), flush=True)
    print(f"Stage 8.2 experiment finished in {summary['wall_time_s']}s", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
