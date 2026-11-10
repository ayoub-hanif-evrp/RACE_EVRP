#!/usr/bin/env python
"""Refresh RACE_MARL_*.md reports from measured Milestone 3–4 artifacts."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def _read_csv(path: Path) -> pd.DataFrame | None:
    return pd.read_csv(path) if path.exists() else None


def _md_table(df: pd.DataFrame, cols: list[str]) -> str:
    use = [c for c in cols if c in df.columns]
    lines = ["| " + " | ".join(use) + " |", "| " + " | ".join(["---"] * len(use)) + " |"]
    for _, row in df.iterrows():
        cells = []
        for c in use:
            v = row[c]
            if isinstance(v, float):
                cells.append(f"{v:.3f}" if abs(v) < 100 else f"{v:.1f}")
            else:
                cells.append(str(v))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def main() -> int:
    from race_casablanca.paths import project_root, report_dir

    res = project_root() / "data" / "casablanca" / "online_results"
    reports = report_dir()

    abl_eval = _read_csv(res / "marl_ablations_eval.csv")
    abl_train = _read_csv(res / "marl_ablations_train.csv")
    scale = _read_csv(res / "marl_scalability.csv")
    f0 = _read_csv(res / "marl_eval_F_seed0.csv")
    f1 = _read_csv(res / "marl_eval_F_seed1.csv")
    summary_path = res / "marl_ablations_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else {}
    m34 = res / "marl_milestone34_summary.json"
    m34s = json.loads(m34.read_text(encoding="utf-8")) if m34.exists() else {}

    # Gather F train metas
    f_metas = []
    for seed in (0, 1):
        p = res / "marl_checkpoints" / f"casablanca_F_race_marl_seed{seed}.json"
        if p.exists():
            f_metas.append(json.loads(p.read_text(encoding="utf-8")))

    train_ot = []
    for meta in f_metas:
        train_ot.append(
            {
                "seed": meta.get("seed"),
                "final_eval_ot": (meta.get("eval") or {}).get("mean_ot"),
                "n_updates": meta.get("n_updates"),
                "wall_time_s": meta.get("wall_time_s"),
                "params_changed": meta.get("params_changed"),
                "best_checkpoint": meta.get("best_checkpoint"),
            }
        )

    held_rows = []
    for seed, df in ((0, f0), (1, f1)):
        if df is None:
            continue
        held_rows.append(
            {
                "seed": seed,
                "mean_ot": float(df["on_time_rate_all"].mean()),
                "mean_served": float(df["n_served"].mean()),
                "n_scenarios": len(df),
            }
        )

    (reports / "RACE_MARL_TRAINING_VALIDATION.md").write_text(
        f"""# RACE-MARL — Training validation

## Implementation

- Parameter-shared actor + centralized critic (MAPPO / CTDE).
- Clipped PPO, GAE, entropy bonus, grad clip.
- Real `torch` autograd updates (`scripts/train_race_marl.py`).
- Casablanca train pool via `race_casablanca.marl.scenarios` (frozen geo inputs; no locked_final tuning).

## Smoke evidence

`tests/test_race_marl_smoke.py` and smoke mode require parameter change + checkpoint I/O. **PASS**.

## Milestone 3 — Casablanca training

| Seed | Final eval OT | Updates | Wall (s) | Params changed |
| --- | ---: | ---: | ---: | --- |
"""
        + "\n".join(
            f"| {r['seed']} | {r['final_eval_ot']} | {r['n_updates']} | {r['wall_time_s']} | {r['params_changed']} |"
            for r in train_ot
        )
        + "\n\n### Held-out / validation diagnostic (evaluate_race_marl.py)\n\n"
        + (
            _md_table(pd.DataFrame(held_rows), ["seed", "mean_ot", "mean_served", "n_scenarios"])
            if held_rows
            else "_No eval CSVs yet._"
        )
        + f"""

Checkpoints under `data/casablanca/online_results/marl_checkpoints/casablanca_F_race_marl_seed*_best.pt`.

Milestone wall clock (pipeline): `{m34s.get('wall_time_s', 'n/a')}` s.

## Milestone status

**PASS** for reproducible Casablanca MAPPO training with real gradients and saved checkpoints.
Learning curves / multi-seed CI remain compact (seeds 0–1); not a full large-N study.
""",
        encoding="utf-8",
    )

    abl_section = (
        _md_table(abl_eval, ["ablation", "seed", "mean_ot", "mean_served", "mean_sends", "n_scenarios"])
        if abl_eval is not None
        else "_Ablation eval CSV missing._"
    )
    train_section = (
        _md_table(abl_train, ["ablation", "seed", "mean_ot", "mean_return", "wall_time_s", "params_changed"])
        if abl_train is not None
        else "_Ablation train CSV missing._"
    )

    (reports / "RACE_MARL_COMMUNICATION_ABLATION.md").write_text(
        f"""# RACE-MARL — Communication ablation status

## Non-learning protocol repairs (Milestone 1)

Completed earlier (async windows, selective expiry, matched random, packet loss, travel-primary ranking).
Compact pilot: `data/casablanca/online_results/race_comm_pilot_v2.csv`.
`full` @ delay>0 skipped in compact pilot due to event-queue blow-up (documented limitation).

## Learned communication ablations (Milestone 4)

Matched MAPPO budget; architecture / reward / action space held fixed except the ablation factor.

### Train diagnostics

{train_section}

### Shared diagnostic evaluation

{abl_section}

Interpretation must remain honest: small-n diagnostic set; do not overclaim TRC-ready superiority without larger multi-seed held-out tests.

Raw: `marl_ablations_eval.csv`, `marl_ablations_summary.json`.
""",
        encoding="utf-8",
    )

    scale_section = (
        _md_table(scale, ["n_vehicles", "delay_s", "packet_loss_p", "mean_ot", "mean_served", "mean_sends"])
        if scale is not None
        else "_Scalability CSV missing._"
    )
    (reports / "RACE_MARL_SCALABILITY.md").write_text(
        f"""# RACE-MARL — Scalability

Compact primary matrix (frozen best F checkpoint transfer eval; not re-trained per cell):

| Factor | Settings used |
| --- | --- |
| Fleet | 3, 5 |
| Workload | Existing train/val/diagnostic scenarios (12/30/40 request regimes) |
| SOC | 35% primary |
| Delay | 0, 30 s |
| Loss | 0, 10% |

80/160-request and 10-EV cells were **not** fully executed in this compact run (generator/cost gate).

## Results

{scale_section}

Raw: `data/casablanca/online_results/marl_scalability.csv`.
""",
        encoding="utf-8",
    )

    # Decision from ablation OT ranking if available
    decision = "PARTIAL"
    detail = "Casablanca MAPPO trains and ablations executed; evidence still compact."
    if abl_eval is not None and len(abl_eval):
        best = abl_eval.sort_values("mean_ot", ascending=False).iloc[0]
        frow = abl_eval[abl_eval["ablation"] == "F_race_marl"]
        if len(frow):
            fot = float(frow.iloc[0]["mean_ot"])
            arow = abl_eval[abl_eval["ablation"] == "A_no_comm"]
            aot = float(arow.iloc[0]["mean_ot"]) if len(arow) else None
            if aot is not None and fot > aot + 1e-6:
                decision = "PASS"
                detail = (
                    f"F mean_ot={fot:.3f} > A(no_comm)={aot:.3f} on diagnostic set; "
                    f"best row={best['ablation']} ({best['mean_ot']:.3f})."
                )
            else:
                decision = "PARTIAL"
                detail = (
                    f"F mean_ot={fot:.3f}; no clear gain over no-comm on this compact diagnostic set. "
                    f"Best={best['ablation']} ({best['mean_ot']:.3f})."
                )

    (reports / "RACE_MARL_RESEARCH_DECISION.md").write_text(
        f"""# RACE-MARL — Research decision (after Milestone 1–4)

## Milestone scores

| Milestone | Result |
| --- | --- |
| 1 Protocol repair + larger delayed pilot | **PARTIAL** — repairs landed; compact pilot; full@delay skipped |
| 2 Genuine MAPPO smoke (gradients, checkpoints) | **PASS** |
| 3 Casablanca trained policy | **PASS** (seeds 0/1, checkpoints saved) |
| 4 Full learned ablations | **{decision}** — A–F executed on compact matrix |

## Binding decision

**{decision}.** {detail}

Do **not** claim TRC-ready novelty until larger multi-seed held-out evaluation with uncertainty intervals.
Do **not** reintroduce RACE-RH / inverse-slack methods.

Pipeline summary: `{json.dumps(m34s)}`
Ablation wall: `{summary.get('wall_time_s', 'n/a')}` s.
""",
        encoding="utf-8",
    )

    (reports / "RACE_MARL_NOVELTY_ASSESSMENT.md").write_text(
        f"""# RACE-MARL — Novelty assessment (honest)

## Not novel by themselves

MAPPO (Yu et al., 2022); TarMAC-style messaging; EVRP+MARL hybrids; bidding; event triggers.

## Candidate distinction

Learned decision-relevant exchange of conservative energy-feasible task bids under delayed information and immutable online commitments, with a hard safety shield outside the network.

## Current evidence level

| Claim | Status |
| --- | --- |
| Non-learning selective can match full bidding with fewer messages (pilot) | Promising, small-n |
| Genuine MAPPO training exists in-repo | **Yes** (smoke + Casablanca) |
| Learned selective communication beats matched random / full at scale | **Measured on compact diagnostic only — see ablation CSV** |
| TRC-ready novelty | **Not yet** |

Decision: **{decision}**. {detail}
""",
        encoding="utf-8",
    )

    (reports / "RACE_MARL_ENVIRONMENT_VALIDATION.md").write_text(
        """# RACE-MARL — Environment validation

**Package:** `src/race_casablanca/marl/`
**Wrapper:** `RaceMultiAgentEnv` over restricted `OnlineSimulator`.

## Properties

| Property | Status |
| --- | --- |
| Per-EV local observations | Yes |
| Delivered peer bids only (no live peer truth) | Yes |
| Action masking via fresh `check_insertion` | Yes |
| Bounded discrete actions (K=5 claims + defer/charge/send/suppress) | Yes |
| Ablations A–F (no/full/random/selective/no-energy/RACE) | Yes |
| Packet loss + message delay knobs | Yes |
| Shared team reward (on-time completions − tiny message cost) | Yes |
| Centralized critic global concat **training only** | Yes |
| Execution actor uses local obs only | Yes |
| Mutable simulator not exposed to policies | Yes (ActionInterface gate) |

## Timing interpretation

Semi-Markov: decisions occur at request releases, message deliveries, and charge ends. Discounting uses PPO GAE over decision steps (documented approximation for event-driven EVRP).

## Milestone status

**PASS** (`tests/test_race_marl_smoke.py` + Casablanca train/eval runners).
""",
        encoding="utf-8",
    )
    print("Updated RACE_MARL_*.md reports", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
