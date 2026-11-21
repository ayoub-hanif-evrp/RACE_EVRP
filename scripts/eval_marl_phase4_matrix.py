#!/usr/bin/env python
"""Phase 4 flagship matrix (smoke / core / full axis product)."""

from __future__ import annotations

import argparse
import itertools
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def _g4_cell(a: float, b: float, f: float, bytes_f: float, bytes_b: float) -> dict:
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


def _summarize(rows: list[dict]) -> dict:
    """Per-cell G4-style summary keyed by regime/bind/seed/delay/loss/nv."""
    groups: dict[tuple, dict[str, dict]] = {}
    for r in rows:
        key = (
            r["regime"],
            bool(r["energy_binding"]),
            int(r["master_seed"]),
            float(r["message_delay_s"]),
            float(r["packet_loss_p"]),
            int(r["n_vehicles"]),
        )
        groups.setdefault(key, {})[r["ablation"]] = r

    cells = []
    n_hard = 0
    n_soft = 0
    for key, abl in sorted(groups.items()):
        regime, bind, seed, delay, loss, nv = key
        a = abl.get("A_no_comm", {})
        b = abl.get("B_full_comm", {})
        f = abl.get("F_race_marl", {})
        if not (a and b and f):
            continue
        crit = _g4_cell(
            float(a["mean_ot"]),
            float(b["mean_ot"]),
            float(f["mean_ot"]),
            float(f["mean_bytes"]),
            float(b["mean_bytes"]),
        )
        if crit["hard_pass"]:
            n_hard += 1
        if crit["soft_pass"]:
            n_soft += 1
        cells.append(
            {
                "regime": regime,
                "energy_binding": bind,
                "master_seed": seed,
                "message_delay_s": delay,
                "packet_loss_p": loss,
                "n_vehicles": nv,
                "A_ot": float(a["mean_ot"]),
                "B_ot": float(b["mean_ot"]),
                "C_ot": float(abl.get("C_random_matched", {}).get("mean_ot", float("nan"))),
                "F_ot": float(f["mean_ot"]),
                "criteria": crit,
            }
        )
    return {
        "n_cells": len(cells),
        "n_hard_pass": n_hard,
        "n_soft_pass": n_soft,
        "cells": cells,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/phase4_matrix.json")
    parser.add_argument(
        "--mode",
        choices=["smoke", "core", "channel", "fleet", "full"],
        default="smoke",
    )
    parser.add_argument("--checkpoint", default=None)
    parser.add_argument(
        "--out",
        default=None,
        help="Default: data/casablanca/online_results/top_tier/phase4/matrix_{mode}.json",
    )
    args = parser.parse_args()

    from race_casablanca.marl.env import (
        ABLATION_A,
        ABLATION_B,
        ABLATION_C,
        ABLATION_F,
        RaceMultiAgentEnv,
    )
    from race_casablanca.marl.mappo import MAPPOTrainer
    from race_casablanca.marl.phase3_eval import _rollout_metrics, regime_factory
    from race_casablanca.paths import project_root
    import torch

    cfg_path = project_root() / args.config
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    if args.mode in ("smoke", "core", "channel", "fleet"):
        axes = dict(cfg[args.mode])
    else:
        axes = {**cfg["axes"], **cfg.get("full", {})}
    episodes = int(axes.get("episodes", cfg.get("full", {}).get("episodes", 4)))
    ckpt = args.checkpoint or cfg["checkpoint_default"]
    abl_map = {
        "A_no_comm": ABLATION_A,
        "B_full_comm": ABLATION_B,
        "C_random_matched": ABLATION_C,
        "F_race_marl": ABLATION_F,
    }

    delays = axes["message_delay_s"]
    losses = axes["packet_loss_p"]
    nvs = axes["n_vehicles"]
    regimes = axes["regime"]
    binds = axes["energy_binding"]
    seeds = axes["master_seed"]

    rows = []
    for delay, loss, nv, regime, bind, seed in itertools.product(
        delays, losses, nvs, regimes, binds, seeds
    ):
        factory = regime_factory(
            regime=regime, master_seed=int(seed), energy_binding=bool(bind), n_vehicles=int(nv)
        )
        for abl_name in cfg["ablations"]:
            abl = abl_map[abl_name]
            print(
                f"eval delay={delay} loss={loss} nv={nv} regime={regime} "
                f"bind={bind} seed={seed} abl={abl_name}",
                flush=True,
            )
            env = RaceMultiAgentEnv(
                scenario_factory=factory,
                n_vehicles=int(nv),
                ablation=abl,
                seed=int(seed),
                max_decisions=2000,
                initial_soc=0.35,
                message_delay_s=float(delay),
                packet_loss_p=float(loss),
                claim_resolve_mode="sequential_native",
            )
            trainer = MAPPOTrainer(env)
            # Actor is fleet-size invariant; critic is n_agents-dependent — actor-only OK for eval.
            ckpt_obj = torch.load(project_root() / ckpt, map_location=trainer.device, weights_only=False)
            trainer.actor.load_state_dict(ckpt_obj["actor"])
            ep_rows = []
            for ep in range(episodes):
                steps = env.reset(seed=ep)
                while True:
                    actions = {}
                    for vid, st in steps.items():
                        o = torch.as_tensor(st.obs, dtype=torch.float32).unsqueeze(0)
                        om = torch.as_tensor(st.op_mask, dtype=torch.float32).unsqueeze(0)
                        cm = torch.as_tensor(st.comm_mask, dtype=torch.float32).unsqueeze(0)
                        with torch.no_grad():
                            op_logits, comm_logits = trainer.actor(o, om, cm)
                        actions[vid] = (
                            int(torch.argmax(op_logits, dim=-1).item()),
                            int(torch.argmax(comm_logits, dim=-1).item()),
                        )
                    steps = env.step(actions)
                    if list(steps.values())[0].done:
                        break
                ep_rows.append(_rollout_metrics(env))
            row = {
                "message_delay_s": float(delay),
                "packet_loss_p": float(loss),
                "n_vehicles": int(nv),
                "regime": regime,
                "energy_binding": bool(bind),
                "master_seed": int(seed),
                "ablation": abl_name,
                "mean_ot": float(sum(r["on_time_rate_all"] for r in ep_rows) / max(1, len(ep_rows))),
                "mean_bytes": float(sum(r["n_bid_bytes"] for r in ep_rows) / max(1, len(ep_rows))),
                "mean_msgs": float(sum(r["n_bid_messages"] for r in ep_rows) / max(1, len(ep_rows))),
                "episodes": ep_rows,
            }
            print(
                f"  ot={row['mean_ot']:.3f} bytes={row['mean_bytes']:.0f} msgs={row['mean_msgs']:.1f}",
                flush=True,
            )
            rows.append(row)

    summary = _summarize(rows)
    out_rel = args.out or f"data/casablanca/online_results/top_tier/phase4/matrix_{args.mode}.json"
    out = project_root() / out_rel
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "mode": args.mode,
        "checkpoint": ckpt,
        "config": str(cfg_path).replace("\\", "/"),
        "n_rows": len(rows),
        "summary": summary,
        "rows": rows,
    }
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ("n_cells", "n_hard_pass", "n_soft_pass")}, indent=2), flush=True)
    print(f"wrote {out} ({len(rows)} rows)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
