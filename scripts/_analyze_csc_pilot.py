#!/usr/bin/env python
"""Print paired CSC pilot contrasts (helper for reports)."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
df = pd.read_csv(ROOT / "data/casablanca/online_results/race_csc_pilot.csv")
s = pd.read_csv(ROOT / "data/casablanca/online_results/race_csc_pilot_summary.csv")
paired = json.loads((ROOT / "data/casablanca/online_results/race_csc_pilot_paired.json").read_text())

print("rows", len(df), "scenarios", df.scenario.nunique())
print("\n=== MEAN OT (loss=0) ===")
print(s[s.packet_loss_p == 0].pivot(index="treatment", columns="delay_s", values="mean_ot").round(4))
print("\n=== MEAN BYTES (loss=0) ===")
print(s[s.packet_loss_p == 0].pivot(index="treatment", columns="delay_s", values="mean_bytes").round(0))
print("\n=== PAIRED ===")
for p in paired:
    if not p.get("n"):
        continue
    print(
        f"{p['left']} vs {p['right']} d={p['delay_s']} loss={p.get('packet_loss_p', 0)}: "
        f"dOT={p['mean_delta_ot_pp']:+.2f}pp+/-{p['std_delta_ot_pp']:.2f} "
        f"dBytes={p['mean_delta_bytes']:+.0f} owner_hamm={p['mean_owner_hamming']:.2f} "
        f"n_diff={p['n_owner_diff_scenarios']}"
    )
