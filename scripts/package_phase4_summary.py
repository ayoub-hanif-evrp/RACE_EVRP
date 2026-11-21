#!/usr/bin/env python
"""Package Phase 4 multi-seed tables with bootstrap CIs (pre-locked freeze)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def _ci(xs: list[float], n_boot: int = 2000, seed: int = 0) -> dict:
    a = np.asarray(xs, dtype=float)
    if a.size == 0:
        return {"mean": float("nan"), "lo": float("nan"), "hi": float("nan"), "n": 0}
    rng = np.random.default_rng(seed)
    means = []
    for _ in range(n_boot):
        samp = rng.choice(a, size=a.size, replace=True)
        means.append(float(samp.mean()))
    lo, hi = np.quantile(means, [0.025, 0.975])
    return {"mean": float(a.mean()), "lo": float(lo), "hi": float(hi), "n": int(a.size)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out",
        default="data/casablanca/online_results/top_tier/phase4/phase4_summary.json",
    )
    args = parser.parse_args()

    from race_casablanca.paths import project_root

    root = project_root()
    tt = root / "data/casablanca/online_results/top_tier"
    g4 = json.loads((tt / "phase3_g4_multiseed.json").read_text(encoding="utf-8"))
    fleet = json.loads((tt / "phase4/matrix_fleet.json").read_text(encoding="utf-8"))
    delay = json.loads((tt / "phase4/delay30_g3_g4.json").read_text(encoding="utf-8"))
    g5 = json.loads((tt / "phase4/g5_nl_charge.json").read_text(encoding="utf-8"))
    energy = json.loads((tt / "phase4/conflict_energy_g4.json").read_text(encoding="utf-8"))

    g4_gaps = [s["criteria"]["F_minus_A"] for s in g4["seeds"]]
    g4_br = [s["criteria"]["bytes_F_over_B"] for s in g4["seeds"]]
    fleet_by_nv: dict[int, list] = {}
    for c in fleet["summary"]["cells"]:
        fleet_by_nv.setdefault(int(c["n_vehicles"]), []).append(c)

    summary = {
        "g4_conflict_delay0_nv3": {
            "F_minus_A": _ci(g4_gaps),
            "bytes_F_over_B": _ci(g4_br),
            "n_hard_pass": g4["summary"]["n_hard_pass"],
            "n_seeds": g4["summary"]["n_seeds"],
        },
        "fleet_axis": {
            str(nv): {
                "n_hard": sum(1 for c in cells if c["criteria"]["hard_pass"]),
                "n_cells": len(cells),
                "F_minus_A": _ci([c["F_ot"] - c["A_ot"] for c in cells], seed=nv),
                "B_minus_A": _ci([c["B_ot"] - c["A_ot"] for c in cells], seed=100 + nv),
                "bytes_F_over_B": _ci([c["criteria"]["bytes_F_over_B"] for c in cells], seed=200 + nv),
            }
            for nv, cells in sorted(fleet_by_nv.items())
        },
        "delay30": delay,
        "energy_binding_g4": energy,
        "g5_nl_charge": {
            "n_hard_pass": g5["summary"]["n_hard_pass"],
            "mean_delta_ot": g5["summary"]["mean_delta_ot"],
            "exact_pass": g5["summary"]["exact"]["pass"],
            "nl_taper_full_over_partial": g5["summary"]["nl_taper"]["full_over_partial"],
            "delta_ot_ci": _ci(
                [s["summary"]["mean_delta_ot"] for s in g5["seeds"]],
                seed=5,
            ),
        },
    }
    out = root / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)
    print(f"wrote {out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
