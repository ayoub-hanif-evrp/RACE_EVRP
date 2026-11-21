#!/usr/bin/env python3
"""Generate top-tier paper figures 1–5 from frozen JSON artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
TOP = ROOT / "data" / "casablanca" / "online_results" / "top_tier"
FIG = ROOT / "reports" / "figures" / "top_tier"

ABLATIONS = ("A_no_comm", "B_full_comm", "C_random_matched", "F_race_marl")
SHORT = {
    "A_no_comm": "A",
    "B_full_comm": "B",
    "C_random_matched": "C",
    "F_race_marl": "F",
}
COLORS = {
    "A": "#4C78A8",
    "B": "#F58518",
    "C": "#54A24B",
    "F": "#E45756",
}


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _style(ax) -> None:
    ax.grid(True, axis="y", alpha=0.3)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)


def fig1_conflict(out: Path) -> None:
    data = _load(TOP / "phase3_g4_multiseed.json")
    seeds = [s["master_seed"] for s in data["seeds"]]
    x = np.arange(len(seeds))
    width = 0.18

    fig, axes = plt.subplots(1, 2, figsize=(9.5, 4.2))

    ax = axes[0]
    for i, key in enumerate(ABLATIONS):
        ots = [s["rows"][key]["mean_ot"] * 100 for s in data["seeds"]]
        ax.bar(x + (i - 1.5) * width, ots, width, label=SHORT[key], color=COLORS[SHORT[key]])
    ax.set_xticks(x)
    ax.set_xticklabels([f"seed {s}" for s in seeds])
    ax.set_ylabel("On-time rate (%)")
    ax.set_title("Conflict stress OT (delay=0, nv=3)")
    ax.legend(frameon=False, ncol=4, loc="upper left")
    _style(ax)

    ax = axes[1]
    br = [s["criteria"]["bytes_F_over_B"] for s in data["seeds"]]
    ax.bar(x, br, color=COLORS["F"], width=0.55)
    ax.axhline(1.0, color="0.4", ls="--", lw=1, label="B bytes")
    ax.set_xticks(x)
    ax.set_xticklabels([f"seed {s}" for s in seeds])
    ax.set_ylabel("Bytes F / B")
    ax.set_ylim(0, 1.15)
    ax.set_title("Bandwidth ratio (F vs full-comm)")
    ax.legend(frameon=False)
    _style(ax)

    fig.tight_layout()
    fig.savefig(out / "fig1_conflict_ot_bytes.png", dpi=200, bbox_inches="tight")
    fig.savefig(out / "fig1_conflict_ot_bytes.pdf", bbox_inches="tight")
    plt.close(fig)


def fig2_delay(out: Path) -> None:
    data = _load(TOP / "phase4" / "delay30_g3_g4.json")
    sanity = data["delay0_seed0_sanity"]
    # delay0 seed0 + delay30 seeds 0–2
    rows = [
        ("0 / s0", sanity["A"], sanity["B"], sanity["F"]),
    ]
    for s in data["seeds"]:
        rows.append((f"30 / s{s['seed']}", s["A"], s["B"], s["F"]))

    labels = [r[0] for r in rows]
    x = np.arange(len(rows))
    width = 0.25
    fig, ax = plt.subplots(figsize=(8.2, 4.2))
    for i, (name, color) in enumerate([("A", COLORS["A"]), ("B", COLORS["B"]), ("F", COLORS["F"])]):
        vals = [r[i + 1] * 100 for r in rows]
        ax.bar(x + (i - 1) * width, vals, width, label=name, color=color)
    ax.set_xticks(x)
    ax.set_xticklabels([f"delay {lab}" for lab in labels])
    ax.set_ylabel("On-time rate (%)")
    ax.set_title("Delay channel: A / B / F (assign-wait)")
    ax.legend(frameon=False)
    _style(ax)
    fig.tight_layout()
    fig.savefig(out / "fig2_delay_g3.png", dpi=200, bbox_inches="tight")
    fig.savefig(out / "fig2_delay_g3.pdf", bbox_inches="tight")
    plt.close(fig)


def fig3_fleet(out: Path) -> None:
    data = _load(TOP / "phase4" / "matrix_fleet.json")
    summary = _load(TOP / "phase4" / "phase4_summary.json")["fleet_axis"]

    nvs = [3, 5, 8]
    # Aggregate mean OT per ablation × nv from rows (delay 0 only)
    means = {nv: {a: [] for a in ABLATIONS} for nv in nvs}
    brs = {nv: [] for nv in nvs}
    for row in data["rows"]:
        if float(row.get("message_delay_s", 0)) != 0.0:
            continue
        nv = int(row["n_vehicles"])
        if nv not in means:
            continue
        means[nv][row["ablation"]].append(float(row["mean_ot"]))
    # bytes ratio from seed-level F/B when both present
    by_seed = {}
    for row in data["rows"]:
        if float(row.get("message_delay_s", 0)) != 0.0:
            continue
        key = (int(row["n_vehicles"]), int(row["master_seed"]))
        by_seed.setdefault(key, {})[row["ablation"]] = row
    for (nv, _seed), ab in by_seed.items():
        if "F_race_marl" in ab and "B_full_comm" in ab:
            b = ab["B_full_comm"]["mean_bytes"]
            f = ab["F_race_marl"]["mean_bytes"]
            if b > 0:
                brs[nv].append(f / b)

    x = np.arange(len(nvs))
    width = 0.18
    fig, axes = plt.subplots(1, 2, figsize=(9.5, 4.2))

    ax = axes[0]
    for i, key in enumerate(ABLATIONS):
        vals = [float(np.mean(means[nv][key])) * 100 if means[nv][key] else 0.0 for nv in nvs]
        ax.bar(x + (i - 1.5) * width, vals, width, label=SHORT[key], color=COLORS[SHORT[key]])
    ax.set_xticks(x)
    ax.set_xticklabels([f"nv={nv}" for nv in nvs])
    ax.set_ylabel("Mean on-time rate (%)")
    ax.set_title("Fleet size: conflict OT")
    ax.legend(frameon=False, ncol=4)
    _style(ax)

    ax = axes[1]
    means_br = []
    los = []
    his = []
    for nv in nvs:
        cell = summary[str(nv)]["bytes_F_over_B"]
        means_br.append(cell["mean"])
        los.append(cell["mean"] - cell["lo"])
        his.append(cell["hi"] - cell["mean"])
    ax.bar(x, means_br, color=COLORS["F"], width=0.55, yerr=[los, his], capsize=4)
    ax.axhline(1.0, color="0.4", ls="--", lw=1)
    ax.set_xticks(x)
    ax.set_xticklabels([f"nv={nv}" for nv in nvs])
    ax.set_ylabel("Bytes F / B (mean ± CI)")
    ax.set_ylim(0, 1.15)
    ax.set_title("Bandwidth vs fleet size")
    _style(ax)

    fig.tight_layout()
    fig.savefig(out / "fig3_fleet_ot_bytes.png", dpi=200, bbox_inches="tight")
    fig.savefig(out / "fig3_fleet_ot_bytes.pdf", bbox_inches="tight")
    plt.close(fig)


def fig4_g5(out: Path) -> None:
    data = _load(TOP / "phase4" / "g5_nl_charge.json")
    taper = data["summary"]["nl_taper"]
    seeds = data["seeds"]

    fig, axes = plt.subplots(1, 2, figsize=(9.5, 4.2))

    ax = axes[0]
    labels = ["partial→0.70", "full→1.00"]
    mins = [taper["partial_to_0_70_s"] / 60.0, taper["full_to_1_00_s"] / 60.0]
    ax.bar(labels, mins, color=["#72B7B2", "#B279A2"])
    ax.set_ylabel("Charge duration (min)")
    ax.set_title(f"NL taper from SOC {taper['soc_from']:.2f} ({taper['full_over_partial']:.2f}×)")
    _style(ax)

    ax = axes[1]
    x = np.arange(len(seeds))
    width = 0.35
    partial = [s["summary"]["mean_partial_ot"] * 100 for s in seeds]
    full = [s["summary"]["mean_full_ot"] * 100 for s in seeds]
    ax.bar(x - width / 2, partial, width, label="partial 0.70", color="#72B7B2")
    ax.bar(x + width / 2, full, width, label="always-full 1.0", color="#B279A2")
    ax.set_xticks(x)
    ax.set_xticklabels([f"seed {s['master_seed']}" for s in seeds])
    ax.set_ylabel("On-time rate (%)")
    ax.set_title("G5 binding online: partial vs full")
    ax.legend(frameon=False)
    _style(ax)

    fig.tight_layout()
    fig.savefig(out / "fig4_g5_nl_charge.png", dpi=200, bbox_inches="tight")
    fig.savefig(out / "fig4_g5_nl_charge.pdf", bbox_inches="tight")
    plt.close(fig)


def fig5_locked(out: Path) -> None:
    data = _load(TOP / "phase5" / "locked_final_g6.json")
    regimes = ["baseline", "peak_stress", "tight_windows"]
    regime_labels = ["baseline", "peak", "tight"]
    x = np.arange(len(regimes))
    width = 0.18

    fig, axes = plt.subplots(1, 2, figsize=(9.5, 4.2))

    ax = axes[0]
    for i, key in enumerate(ABLATIONS):
        vals = [data["per_regime"][r][key]["mean"] * 100 for r in regimes]
        ax.bar(x + (i - 1.5) * width, vals, width, label=SHORT[key], color=COLORS[SHORT[key]])
    ax.set_xticks(x)
    ax.set_xticklabels(regime_labels)
    ax.set_ylabel("Mean on-time rate (%)")
    ax.set_title("Locked holdout by regime (G6)")
    ax.legend(frameon=False, ncol=4)
    _style(ax)

    ax = axes[1]
    overall = data["overall"]
    labels = [SHORT[k] for k in ABLATIONS]
    ots = [overall[k]["ot"]["mean"] * 100 for k in ABLATIONS]
    lo = [overall[k]["ot"]["mean"] * 100 - overall[k]["ot"]["lo"] * 100 for k in ABLATIONS]
    hi = [overall[k]["ot"]["hi"] * 100 - overall[k]["ot"]["mean"] * 100 for k in ABLATIONS]
    ax.bar(
        labels,
        ots,
        color=[COLORS[s] for s in labels],
        yerr=[lo, hi],
        capsize=4,
    )
    ax.set_ylabel("On-time rate (%)")
    ax.set_title("Locked overall OT (95% CI)")
    _style(ax)

    fig.tight_layout()
    fig.savefig(out / "fig5_locked_regimes.png", dpi=200, bbox_inches="tight")
    fig.savefig(out / "fig5_locked_regimes.pdf", bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=FIG)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    fig1_conflict(args.out)
    fig2_delay(args.out)
    fig3_fleet(args.out)
    fig4_g5(args.out)
    fig5_locked(args.out)
    print(f"Wrote figures to {args.out}")


if __name__ == "__main__":
    main()
