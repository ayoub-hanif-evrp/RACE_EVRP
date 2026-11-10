#!/usr/bin/env python
"""Evaluate a trained RACE-MARL checkpoint on validation / diagnostic scenarios."""

from __future__ import annotations

import argparse
import json
import sys
import time
from copy import deepcopy
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--checkpoint",
        default="data/casablanca/online_results/marl_checkpoints/casablanca_F_seed0_best.pt",
    )
    parser.add_argument("--ablation", default="F_race_marl")
    parser.add_argument("--n-vehicles", type=int, default=3)
    parser.add_argument("--soc", type=float, default=0.35)
    parser.add_argument("--delay", type=float, default=0.0)
    parser.add_argument("--packet-loss", type=float, default=0.0)
    parser.add_argument("--max-decisions", type=int, default=500)
    parser.add_argument(
        "--out",
        default="data/casablanca/online_results/marl_eval.csv",
    )
    args = parser.parse_args()

    import torch
    from race_casablanca.marl.env import RaceMultiAgentEnv
    from race_casablanca.marl.mappo import MAPPOTrainer
    from race_casablanca.marl.scenarios import resolve_eval_dirs
    from race_casablanca.paths import project_root
    from race_casablanca.sim.scenario_loader import load_congestion_model, load_drive_graph, load_scenario
    from race_casablanca.sim.types import RequestStatus

    ckpt = project_root() / args.checkpoint
    if not ckpt.exists():
        # fall back to non-_best
        alt = ckpt.with_name(ckpt.name.replace("_best.pt", ".pt"))
        if alt.exists():
            ckpt = alt
        else:
            raise SystemExit(f"Missing checkpoint: {args.checkpoint}")

    print("Loading network...", flush=True)
    graph = load_drive_graph()
    model = load_congestion_model()
    paths = resolve_eval_dirs()
    if not paths:
        raise SystemExit("No evaluation scenarios found")

    rows = []
    for path in paths:
        sc = load_scenario(path, load_network=False, graph=graph, model=model)

        def factory(seed: int = 0, n_vehicles: int = args.n_vehicles, _sc=sc):
            reqs = deepcopy(_sc.requests)
            for r in reqs:
                r.status = RequestStatus.UNRELEASED
                r.owner = None
            return {
                "scenario_id": f"{_sc.scenario_id}/eval",
                "graph": graph,
                "model": model,
                "requests": reqs,
                "fleet": {**_sc.fleet, "n_vehicles": n_vehicles},
                "depot_node": _sc.depot_node,
                "shift_start_s": _sc.shift_start_s,
                "shift_end_s": _sc.shift_end_s,
                "day": getattr(_sc, "day", "Monday"),
            }

        env = RaceMultiAgentEnv(
            scenario_factory=factory,
            n_vehicles=args.n_vehicles,
            initial_soc=args.soc,
            message_delay_s=args.delay,
            packet_loss_p=args.packet_loss,
            ablation=args.ablation,
            seed=0,
            max_decisions=args.max_decisions,
        )
        trainer = MAPPOTrainer(env)
        trainer.load(ckpt)
        t0 = time.time()
        steps = env.reset(seed=0)
        done = False
        total_r = 0.0
        while not done:
            actions = {}
            for vid, st in steps.items():
                o = torch.as_tensor(st.obs, dtype=torch.float32, device=trainer.device).unsqueeze(0)
                om = torch.as_tensor(st.op_mask, dtype=torch.float32, device=trainer.device).unsqueeze(0)
                cm = torch.as_tensor(st.comm_mask, dtype=torch.float32, device=trainer.device).unsqueeze(0)
                op_logits, comm_logits = trainer.actor(o, om, cm)
                op_a = int(torch.argmax(op_logits, dim=-1).item())
                comm_a = int(torch.argmax(comm_logits, dim=-1).item())
                actions[vid] = (op_a, comm_a)
            steps = env.step(actions)
            total_r += list(steps.values())[0].reward
            done = list(steps.values())[0].done
        metrics = env.final_metrics()
        row = {
            "scenario": path.name,
            "checkpoint": str(ckpt).replace("\\", "/"),
            "ablation": args.ablation,
            "n_vehicles": args.n_vehicles,
            "initial_soc": args.soc,
            "delay_s": args.delay,
            "packet_loss_p": args.packet_loss,
            "return": total_r,
            "on_time_rate_all": metrics.get("on_time_rate_all"),
            "n_served": metrics.get("n_served"),
            "n_requests": metrics.get("n_requests"),
            "bid_msgs": metrics.get("n_bid_messages", metrics.get("bid_messages")),
            "n_send_actions": metrics.get("n_send_actions"),
            "n_op_claims": metrics.get("n_op_claims"),
            "n_decisions": metrics.get("n_decisions"),
            "wall_s": round(time.time() - t0, 2),
        }
        # pull common metric keys if present
        for k in (
            "energy_consumed_kwh",
            "total_distance_m",
            "n_charges",
            "battery_reserve_violations",
            "n_messages_sent",
        ):
            if k in metrics:
                row[k] = metrics[k]
        rows.append(row)
        print(
            f"{path.name}: ot={row['on_time_rate_all']:.3f} served={row['n_served']}/{row['n_requests']} "
            f"sends={row['n_send_actions']} ({row['wall_s']}s)",
            flush=True,
        )

    out = project_root() / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows)
    df.to_csv(out, index=False)
    summary = {
        "n": len(df),
        "mean_ot": float(df["on_time_rate_all"].mean()),
        "mean_served": float(df["n_served"].mean()),
        "checkpoint": str(ckpt).replace("\\", "/"),
        "ablation": args.ablation,
    }
    out.with_suffix(".json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)
    print(f"Wrote {out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
