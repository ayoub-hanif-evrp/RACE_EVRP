#!/usr/bin/env python
"""G6: one-shot locked_final holdout eval (A/B/C/F). Do not retune after this run."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _bootstrap_ci(xs: list[float], n_boot: int = 2000, seed: int = 0) -> dict:
    import numpy as np

    a = np.asarray(xs, dtype=float)
    if a.size == 0:
        return {"mean": float("nan"), "lo": float("nan"), "hi": float("nan"), "n": 0}
    rng = np.random.default_rng(seed)
    boots = [float(rng.choice(a, size=a.size, replace=True).mean()) for _ in range(n_boot)]
    lo, hi = np.quantile(boots, [0.025, 0.975])
    return {"mean": float(a.mean()), "lo": float(lo), "hi": float(hi), "n": int(a.size)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--checkpoint",
        default="data/casablanca/online_results/top_tier/marl_checkpoints/phase3_F_conflict_g4mask_seed0_best.pt",
    )
    parser.add_argument(
        "--locked-root",
        default="data/casablanca/evaluation_v1/locked_final",
    )
    parser.add_argument(
        "--out",
        default="data/casablanca/online_results/top_tier/phase5/locked_final_g6.json",
    )
    parser.add_argument(
        "--freeze-out",
        default="data/casablanca/online_results/top_tier/phase5/freeze_manifest.json",
    )
    parser.add_argument("--max-scenarios", type=int, default=0, help="0 = all")
    args = parser.parse_args()

    import subprocess

    import torch
    import yaml
    from race_casablanca.marl.env import (
        ABLATION_A,
        ABLATION_B,
        ABLATION_C,
        ABLATION_F,
        RaceMultiAgentEnv,
    )
    from race_casablanca.marl.mappo import MAPPOTrainer
    from race_casablanca.paths import project_root
    from race_casablanca.sim.scenario_loader import load_congestion_model, load_drive_graph, load_scenario

    root = project_root()
    ckpt_path = root / args.checkpoint
    locked_root = root / args.locked_root
    fleet_yaml = root / "configs/fleet_default.yaml"
    fleet_defaults = yaml.safe_load(fleet_yaml.read_text(encoding="utf-8"))

    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
        dirty = bool(
            subprocess.check_output(["git", "status", "--porcelain"], cwd=root, text=True).strip()
        )
    except Exception:
        commit = "unknown"
        dirty = True

    freeze = {
        "gate": "G6_freeze",
        "git_commit": commit,
        "git_working_tree_dirty": dirty,
        "checkpoint": str(args.checkpoint).replace("\\", "/"),
        "checkpoint_sha256": _sha256(ckpt_path),
        "fleet_default_sha256": _sha256(fleet_yaml),
        "marl_training_protocol_sha256": _sha256(root / "configs/marl_training_protocol.json"),
        "phase4_matrix_sha256": _sha256(root / "configs/phase4_matrix.json"),
        "locked_root": str(args.locked_root).replace("\\", "/"),
        "ablations": ["A_no_comm", "B_full_comm", "C_random_matched", "F_race_marl"],
        "note": "Frozen before locked_final run. Do not retune after reading locked numbers.",
    }
    freeze_path = root / args.freeze_out
    freeze_path.parent.mkdir(parents=True, exist_ok=True)
    freeze_path.write_text(json.dumps(freeze, indent=2), encoding="utf-8")
    print(json.dumps(freeze, indent=2), flush=True)
    print(f"wrote freeze {freeze_path}", flush=True)

    graph = load_drive_graph()
    model = load_congestion_model()
    dirs = sorted([p for p in locked_root.iterdir() if p.is_dir()])
    if args.max_scenarios > 0:
        dirs = dirs[: int(args.max_scenarios)]

    abl_map = {
        "A_no_comm": ABLATION_A,
        "B_full_comm": ABLATION_B,
        "C_random_matched": ABLATION_C,
        "F_race_marl": ABLATION_F,
    }
    actor_state = torch.load(ckpt_path, map_location="cpu", weights_only=False)["actor"]

    rows = []
    for i, sdir in enumerate(dirs):
        sc = load_scenario(sdir, load_network=False, graph=graph, model=model)
        meta = sc.metadata or {}
        regime = str(meta.get("regime", "unknown"))
        fleet = dict(sc.fleet)
        # Ensure NL charging curve from frozen fleet defaults.
        if "charging_curve" not in fleet and fleet_defaults.get("charging_curve"):
            fleet["charging_curve"] = deepcopy(fleet_defaults["charging_curve"])
        nv = int(fleet.get("n_vehicles", 3))
        reqs_template = sc.requests

        def factory(seed: int = 0, n_vehicles: int = nv, _reqs=reqs_template, _fleet=fleet, _sc=sc):
            from race_casablanca.sim.types import RequestStatus

            reqs = deepcopy(_reqs)
            for r in reqs:
                r.status = RequestStatus.UNRELEASED
                r.owner = None
            return {
                "scenario_id": f"{_sc.scenario_id}/locked",
                "graph": graph,
                "model": model,
                "requests": reqs,
                "fleet": dict(_fleet),
                "depot_node": _sc.depot_node,
                "shift_start_s": _sc.shift_start_s,
                "shift_end_s": _sc.shift_end_s,
                "day": getattr(_sc, "day", "Monday"),
            }

        for abl_name, abl in abl_map.items():
            print(f"[{i+1}/{len(dirs)}] {sdir.name} {abl_name}", flush=True)
            env = RaceMultiAgentEnv(
                scenario_factory=factory,
                n_vehicles=nv,
                ablation=abl,
                seed=int(meta.get("seed", 0) or 0),
                max_decisions=4000,
                initial_soc=float(fleet.get("initial_soc", 1.0)),
                message_delay_s=0.0,
                packet_loss_p=0.0,
                claim_resolve_mode="sequential_native",
            )
            trainer = MAPPOTrainer(env)
            trainer.actor.load_state_dict(actor_state)
            steps = env.reset(seed=0)
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
            m = env.final_metrics()
            row = {
                "scenario": sdir.name,
                "regime": regime,
                "ablation": abl_name,
                "on_time_rate_all": float(m.get("on_time_rate_all", 0.0)),
                "n_served": float(m.get("n_served", 0.0)),
                "n_bid_messages": float(m.get("n_bid_messages", 0.0)),
                "n_bid_bytes": float(m.get("n_bid_bytes", 0.0)),
            }
            print(
                f"  ot={row['on_time_rate_all']:.3f} bytes={row['n_bid_bytes']:.0f} msgs={row['n_bid_messages']:.0f}",
                flush=True,
            )
            rows.append(row)

    by_regime_abl: dict[tuple[str, str], list[float]] = defaultdict(list)
    by_abl: dict[str, list[float]] = defaultdict(list)
    by_abl_bytes: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        by_regime_abl[(r["regime"], r["ablation"])].append(r["on_time_rate_all"])
        by_abl[r["ablation"]].append(r["on_time_rate_all"])
        by_abl_bytes[r["ablation"]].append(r["n_bid_bytes"])

    overall = {
        abl: {
            "ot": _bootstrap_ci(xs, seed=hash(abl) % 10000),
            "bytes": _bootstrap_ci(by_abl_bytes[abl], seed=17 + hash(abl) % 10000),
        }
        for abl, xs in by_abl.items()
    }
    per_regime = {}
    for (regime, abl), xs in sorted(by_regime_abl.items()):
        per_regime.setdefault(regime, {})[abl] = _bootstrap_ci(xs, seed=hash(regime + abl) % 10000)

    a = overall.get("A_no_comm", {}).get("ot", {}).get("mean", 0.0)
    b = overall.get("B_full_comm", {}).get("ot", {}).get("mean", 0.0)
    f = overall.get("F_race_marl", {}).get("ot", {}).get("mean", 0.0)
    bb = overall.get("B_full_comm", {}).get("bytes", {}).get("mean", 1.0)
    fb = overall.get("F_race_marl", {}).get("bytes", {}).get("mean", 0.0)
    payload = {
        "gate": "G6",
        "freeze_manifest": str(args.freeze_out).replace("\\", "/"),
        "checkpoint": str(args.checkpoint).replace("\\", "/"),
        "n_scenarios": len(dirs),
        "n_rows": len(rows),
        "overall": overall,
        "per_regime": per_regime,
        "headline": {
            "F_minus_A": float(f - a),
            "F_minus_B": float(f - b),
            "B_minus_A": float(b - a),
            "bytes_F_over_B": float(fb / max(1.0, bb)),
        },
        "rows": rows,
        "note": "One-shot locked_final. Policy/hyperparams frozen; no retune allowed.",
    }
    out = root / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps({"headline": payload["headline"], "overall_ot": {k: v["ot"] for k, v in overall.items()}}, indent=2), flush=True)
    print(f"wrote {out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
