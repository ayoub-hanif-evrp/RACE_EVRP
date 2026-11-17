#!/usr/bin/env python
import json
from pathlib import Path

import pandas as pd

s = pd.read_csv("data/casablanca/online_results/final_locked/final_locked_summary.csv")
print(s.pivot_table(index="treatment", columns="delay_s", values="mean_ot").round(4).to_string())
print("---BYTES---")
print(s.pivot_table(index="treatment", columns="delay_s", values="mean_attempted_bytes").round(0).to_string())
print("---SAFETY---")
print(s.groupby("treatment")[["sum_reserve", "sum_exhaust", "sum_strand"]].sum().to_string())
paired = json.loads(Path("data/casablanca/online_results/final_locked/final_locked_paired.json").read_text(encoding="utf-8"))
print("---PAIRED---")
for p in paired:
    if p.get("n", 0) < 2:
        continue
    print(
        f"{p['left']} vs {p['right']} d={p['delay_s']}: "
        f"dOT={p['mean_delta_ot_pp']:+.2f} [{p['ci95_lo_pp']:+.2f},{p['ci95_hi_pp']:+.2f}] "
        f"lo05={p.get('onesided05_lower_pp')} W/T/L={p['wins']}/{p['ties']}/{p['losses']} "
        f"hamm={p['mean_owner_hamming']:.2f} byte_ratio={p.get('byte_ratio_means')} "
        f"E_L={p.get('mean_left_energy_kwh')}"
    )
