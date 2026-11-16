#!/usr/bin/env python
import json
from pathlib import Path

import pandas as pd

OUT = Path("data/casablanca/online_results/prompt2")
prim = pd.read_csv(OUT / "race_prompt2_primary.csv")
abl = pd.read_csv(OUT / "race_prompt2_ablations.csv") if (OUT / "race_prompt2_ablations.csv").exists() else None
sc = pd.read_csv(OUT / "race_prompt2_scale.csv") if (OUT / "race_prompt2_scale.csv").exists() else None
paired = json.loads((OUT / "race_prompt2_primary_paired.json").read_text(encoding="utf-8"))

print("PRIMARY", len(prim), "ok", int(prim.ok.sum()), "fail", int((~prim.ok).sum()))
print("ABL", None if abl is None else (len(abl), int(abl.ok.sum())))
print("SCALE", None if sc is None else (len(sc), int(sc.ok.sum())))
print("figures", list(Path("reports/figures/prompt2").glob("*")))

print("\n=== PAIRED ===")
for p in paired:
    if p.get("n", 0) < 2:
        continue
    print(
        f"{p['left']} vs {p['right']} d={p['delay_s']} loss={p.get('packet_loss_p', 0)}: "
        f"dOT={p['mean_delta_ot_pp']:+.2f}pp [{p['ci95_lo_pp']:+.2f},{p['ci95_hi_pp']:+.2f}] "
        f"W/T/L={p['wins']}/{p['ties']}/{p['losses']} hamm={p['mean_owner_hamming']:.2f} "
        f"dBytes={p['mean_delta_attempted_bytes']:+.0f} "
        f"E_L={p.get('mean_left_energy_kwh', float('nan')):.2f} ms_L={p.get('mean_left_decision_ms', float('nan')):.1f}"
    )

s = (
    prim[prim.ok]
    .groupby(["treatment", "delay_s", "packet_loss_p"], as_index=False)
    .agg(
        n=("scenario", "nunique"),
        mean_ot=("on_time_rate_all", "mean"),
        mean_bytes=("n_bid_attempted_bytes", "mean"),
        mean_deliv=("n_bid_delivered_bytes", "mean"),
        mean_E=("energy_consumed_kwh", "mean"),
        mean_chg=("energy_delivered_kwh", "mean"),
        mean_ms=("mean_decision_runtime_ms", "mean"),
        sum_reserve=("battery_reserve_violations", "sum"),
    )
)
print("\n=== OT matrix loss=0 ===")
print(s[s.packet_loss_p == 0].pivot_table(index="treatment", columns="delay_s", values="mean_ot").round(4).to_string())
print("\n=== BYTES matrix loss=0 ===")
print(
    s[s.packet_loss_p == 0]
    .pivot_table(index="treatment", columns="delay_s", values="mean_bytes")
    .round(0)
    .to_string()
)

if abl is not None:
    print("\n=== ABLATION OT ===")
    a = (
        abl[abl.ok]
        .groupby(["treatment", "delay_s"], as_index=False)
        .agg(mean_ot=("on_time_rate_all", "mean"), mean_bytes=("n_bid_attempted_bytes", "mean"), n=("scenario", "nunique"))
    )
    print(a.pivot_table(index="treatment", columns="delay_s", values="mean_ot").round(4).to_string())

if sc is not None:
    print("\n=== SCALE fleet OT delay0 ===")
    sf = sc[sc.ok & (sc.phase == "scale_fleet") & (sc.delay_s == 0)]
    print(sf.groupby(["treatment", "n_vehicles"]).on_time_rate_all.mean().unstack().round(4).to_string())
    print("\n=== SCALE SOC ===")
    ss = sc[sc.ok & (sc.phase == "scale_soc")]
    print(ss.groupby(["treatment", "initial_soc"]).agg(mean_ot=("on_time_rate_all", "mean"), mean_E=("energy_consumed_kwh", "mean")).round(4).to_string())
