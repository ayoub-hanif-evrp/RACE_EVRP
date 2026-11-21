# Top-Tier RACE-MARL — Results Tables (filled)

**Checkpoint:** `phase3_F_conflict_g4mask_seed0_best.pt`  
**Freeze:** `data/casablanca/online_results/top_tier/phase5/freeze_manifest.json`  
**Rule:** numbers below are frozen for writing; do not retune.

Ablations: **A** no-comm · **B** full-comm · **C** random matched · **F** RACE-MARL (hero).

---

## 1. Conflict stress — selective value (G4, delay 0, nv=3)

Source: `phase3_g4_multiseed.json` / CIs in `phase4/phase4_summary.json`.

| Seed | A OT | B OT | C OT | F OT | F−A | F−B | bytes F/B | G4 |
|------|------|------|------|------|-----|-----|-----------|-----|
| 0 | 0.354 | 0.438 | 0.396 | **0.438** | +0.083 | 0.000 | 0.60 | hard |
| 1 | 0.292 | 0.375 | 0.333 | **0.375** | +0.083 | 0.000 | 0.62 | hard |
| 2 | 0.323 | 0.354 | 0.344 | **0.375** | +0.052 | +0.021 | 0.69 | hard |

**Aggregate (n=3 seeds):** F−A mean **+7.3 pp** [5.2, 8.3]; bytes F/B mean **0.64** [0.60, 0.69]. Hard pass **3/3**.

**Takeaway:** On conflict_dense, F matches or beats B at ~36% fewer bytes than full-comm, and clearly beats A and C.

---

## 2. Delay channel (G3 under 30 s)

Source: `phase4/delay30_g3_g4.json`.

| Seed | delay | A | B | F | B−A | F−B | bytes F/B | G4 |
|------|-------|---|---|---|-----|-----|-----------|-----|
| 0 | 0 | 0.354 | 0.438 | 0.438 | +0.083 | 0.000 | 0.60 | hard |
| 0 | 30 | 0.354 | 0.438 | 0.438 | +0.083 | 0.000 | 0.53 | hard |
| 1 | 30 | 0.292 | 0.385 | 0.375 | +0.094 | −0.010 | 0.53 | hard |
| 2 | 30 | 0.323 | 0.354 | 0.333 | +0.031 | −0.021 | 0.56 | soft |

**Takeaway:** Assign-wait restores load-bearing comm under delay (B≪̸A). G4 hard **2/3** at 30 s.

---

## 3. Fleet size (nv ∈ {3,5,8})

Source: `phase4/matrix_fleet.json`.

| nv | Seed | A | B | F | B−A | bytes F/B | G4 |
|----|------|---|---|---|-----|-----------|-----|
| 3 | 0–2 | — | — | — | +3–8 pp | 0.60–0.69 | **3/3 hard** |
| 5 | 0 | 0.667 | 0.823 | **0.833** | +0.156 | 0.44 | hard |
| 5 | 1 | 0.479 | 0.583 | **0.583** | +0.104 | 0.44 | hard |
| 5 | 2 | 0.490 | 0.750 | **0.760** | +0.260 | 0.54 | hard |
| 8 | 0 | 0.938 | 0.958 | 0.958 | +0.021 | 0.28 | soft |
| 8 | 1 | 0.833 | 0.906 | 0.896 | +0.073 | 0.34 | hard |
| 8 | 2 | 0.927 | 0.927 | 0.927 | 0.000 | 0.35 | fail |

**CIs (F−A):** nv3 **+7.3 pp** [5.2, 8.3]; nv5 **+18.1 pp** [10.4, 27.1]; nv8 **+2.8 pp** [0, 6.3].

**Takeaway:** Strongest comm value at nv=5. nv=8 is an easy-fleet OT ceiling (A≈B≈F), not a selective-comm failure — F still uses ~32% of B’s bytes.

Spot-check delay=30, nv=5, seed0: B−A **+14.6 pp**, F≈B, br=0.47 (hard).

---

## 4. Energy-binding G4 + G5 NL charge

### 4a. G4 under energy_binding (conflict)

Source: `phase4/conflict_energy_g4.json` — hard **6/6** (bind T/F × seeds 0–2), bytes F/B ≈ 0.59–0.69.

### 4b. G5: partial (0.70) vs always-full (1.0)

Source: `phase4/g5_nl_charge.json`.

| Evidence | Result |
|----------|--------|
| NL taper SOC 0.28→0.70 vs →1.0 | **46.0 vs 113.4 min (2.46×)** |
| Exact `C_partial_better` | best OT=1, always-full=0 |
| Online binding seeds (mean ΔOT) | **+1.4 pp** [0.0, 2.1]; hard **2/3** |
| Charge wall-clock | partial ~**2.3×** less than full |

**Takeaway:** CV taper makes always-full expensive; partial NL targets improve or match OT with far less charge time.

---

## 5. Locked holdout (G6) — one-shot

Source: `phase5/locked_final_g6.json` (30 scenarios × A/B/C/F).  
**Not** conflict_dense; baseline/peak/tight from `evaluation_v1/locked_final`.

### Overall (bootstrap 95% CI across 30 scenarios)

| Ablation | OT | bytes |
|----------|-----|-------|
| A | 0.794 [0.719, 0.859] | 0 |
| B | 0.806 [0.727, 0.876] | 49.1k [40.6k, 58.1k] |
| C | 0.803 [0.729, 0.872] | 19.2k |
| **F** | **0.806** [0.727, 0.874] | **27.7k (0.57×B)** |

Headline: F−A **+1.2 pp**, F−B **0.0**, bytes F/B **0.57**.

### By regime (mean OT)

| Regime | A | B | C | F |
|--------|---|---|---|---|
| baseline | 0.942 | 0.942 | 0.942 | 0.942 |
| peak_stress | 0.840 | **0.860** | 0.850 | **0.860** |
| tight_windows | 0.600 | **0.617** | 0.617 | **0.617** |

**Honesty:** Locked holdout is mostly non-conflict; G3 gap is small by design. Peak/tight still show F=B ≥ A at lower bytes. Primary selective-comm claim remains the conflict stress tables (§1–3).

---

## 6. Figures (generated)

Script: `scripts/plot_top_tier_figures.py` → `reports/figures/top_tier/`.

| Fig | Content | Files |
|-----|---------|-------|
| 1 | Conflict A/B/C/F OT + bytes | `fig1_conflict_ot_bytes.{png,pdf}` |
| 2 | Delay 0 vs 30 G3 | `fig2_delay_g3.{png,pdf}` |
| 3 | Fleet nv OT / bytes | `fig3_fleet_ot_bytes.{png,pdf}` |
| 4 | NL taper + G5 OT | `fig4_g5_nl_charge.{png,pdf}` |
| 5 | Locked regime + overall | `fig5_locked_regimes.{png,pdf}` |

---

## 7. What not to claim

- Do not claim large locked_final B−A (holdout is not conflict_dense).  
- Do not treat nv=8 soft/fail as a method failure (ceiling).  
- Do not present BC-only as the hero — F is MAPPO-fine-tuned selective+cert.  
- Training demand is synthetic / geographically grounded, not observed courier orders.
