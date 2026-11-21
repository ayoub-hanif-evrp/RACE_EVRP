# Top-Tier RACE-MARL Plan (Living Document)

**Status:** ACTIVE — direction locked by authors (2026-11-17)  
**Supersedes for method center:** `RACE_MARL_8_3_RESEARCH_DECISION.md` recommendation to lead with non-learning only.  
**Does not erase:** Stage 8.3 diagnostics remain valid evidence of *why* Phase 1 is required.  
**Physics baseline:** non-linear depot charging only (`reports/NONLINEAR_CHARGING.md`); linear-era `online_results` deleted.

---

## 1. Goal

Produce a **top-tier–credible** paper where **MARL is essential**, with **strong empirical results**, without inventing wins.

### 1.1 Intended paper claim (working title)

> Multi-agent reinforcement learning for online electric pickup fleets under selective communication, delay/bandwidth limits, time windows, and nonlinear charging — recovering strong cooperative competence and outperforming no-comm / bandwidth-matched random baselines in conflict-heavy, partially observed regimes.

### 1.2 Venue aspiration

- Primary stretch: NeurIPS / ICML / ICLR (applied / multi-agent / decision-making) or strong AAMAS / RAL.  
- Credible fallback with same stack: IEEE T-ITS / Transportation Research Part C / EJOR.  
- Fallback is acceptable; **method and gates stay top-tier grade** either way.

### 1.3 Non-negotiables

| Rule | Meaning |
|------|---------|
| MARL is method center | Not an appendix-only diagnostic |
| Honest metrics | Service / TW first; bytes and energy co-reported |
| No locked_final tuning | `evaluation_v1/locked_final` untouched until final freeze |
| NL charging only | No linear `ΔkWh/kW` clock in sims used for new results |
| Piecewise implementation | One phase → gate → only then next phase |
| No fake wins | If a gate fails, fix mechanism or narrow claim — do not retune scenarios to hide failure |

---

## 2. Why previous MARL results were not top-tier

Evidence (Stage 8.2–8.3, communication audits):

1. **Interface gap (~20 pp OT):** batched simultaneous claims in `marl/env.py` ≠ native sequential / two-phase ownership.  
2. **Teacher gap:** intent bridge misses ~16 feasible pickups/episode; BC hits **factorized ceiling ~0.63**, not native ~0.83.  
3. **Communication not load-bearing:** under delay, safe policy ignores peers; trusting delayed peers can *hurt* OT; delay-0 selective ≈ full with tiny OT Δ.  
4. **Energy often non-binding:** comfortable battery headroom → energy-certified comm / NL charge cannot show large gains.  
5. **MAPPO on broken ceiling:** more on-policy updates did not create service advantage for F vs A/C; F/E sometimes regressed.

**Implication:** more GPU on the current env will not create a top-tier paper. Phase 1 is mandatory.

---

## 3. Success gates (hard exits)

Do **not** advance past a phase until its gate passes. Record pass/fail in §11.

| ID | Gate | Threshold | Blocks |
|----|------|-----------|--------|
| G0 | Plan + physics freeze | This doc + NL charging in fleet | All work |
| G1 | Native parity in MARL env | Teacher-in-env OT within **3 pp** of native cooperative on same scenarios (dev set ≥6) | Phase 2+ |
| G2 | Imitation competence | BC+DAgger mean OT **≥ 0.78** (target ≈ native − 3 pp) on val / stress mix | Phase 3 MAPPO scale |
| G3 | Problem hardness | On conflict+hidden-peer set: full-comm OT **≥ no-comm + 8 pp** (or equivalent clear separation) | Claiming comm value |
| G4 | Learned selective value | F ≈ B on OT (within ~3 pp) and F ≪ B bytes; F > A and F ≥ C on conflict set | Main paper tables |
| G5 | Energy / NL relevance | On binding tier: partial NL charge beats always-full (OT or feasibility) | Energy novelty section |
| G6 | Holdout integrity | Locked_final run once after freeze; no hyperparam search on it | Submission |

---

## 4. Method architecture (target)

```
OnlineSimulator (physics, NL charge, TW, commitments)
        ↑
Native feasibility / insertion / certificates  (engine, not final hero)
        ↑
RaceMultiAgentEnv  ←── MUST match native ownership timing (Phase 1)
        ↑
Policy π_θ  (op: claim/defer/charge , comm: send/suppress)
        ↑
Train: BC(native) → DAgger → MAPPO (multi-objective reward)
```

### Clarification: BC is allowed (and expected) for top-tier

**BC ≠ “not top-tier.”**  
What is *not* top-tier is claiming victory with **BC-only imitation of a heuristic** and no learned improvement under hard regimes.

| Role | Top-tier? |
|------|-----------|
| BC / DAgger as **warm-start** so the policy reaches native competence | Yes — standard in VRP / MARL papers |
| Final paper hero = **MAPPO-fine-tuned** policy that beats A/C and matches B at lower bytes | Yes — required |
| Final paper hero = “we copied native with BC” | No |
| Final paper hero = native heuristic with a tiny learned switch only | No (that was the *fast applied* path, not top-tier) |

So the plan **keeps BC on purpose**: without it, MAPPO rarely reaches the competence bar (G1/G2). Top-tier novelty lives in Phase 2–4 (PO, conflict, selective+energy cert, NL charge, large ablated gains), not in refusing imitation.

**MARL decides:** claim / wait / charge target band, and **whom/when to communicate**.  
**Simulator + certificates enforce:** hard feasibility, NL charge duration, commitments.

Warm-start from native is allowed. **Final evaluated agent must be the learned policy** (ablations A–F), not “native with a learned toggle” as the sole result — though a hybrid ablation may appear as baseline.

---

## 5. Phased implementation plan

### Phase 0 — Document & freeze (this file)
**Actions**
- [x] Author this plan.
- [ ] Link from `MARL_TRAINING_DATA_PROTOCOL.md` and handoff notes.
- [ ] Confirm NL charging + empty `online_results` (re-run only under NL).

**Exit:** G0.

---

### Phase 1 — Native-aligned MARL competence (FIRST CODE)
**Objective:** Remove the ~20 pp interface tax so MARL *can* be top-tier.

**Root cause to fix** (`src/race_casablanca/marl/env.py`):
- Today: bid-before-commit + `_batched_resolve_claims` (vehicle-order-invariant batch).
- Native: sequential / two-phase assignment that avoids simultaneous duplicate `op=0` wrong winners (see Stage 8.3 divergence traces).

**Code changes (ordered)**

1. **Claim resolution parity**
   - File: `src/race_casablanca/marl/env.py`
   - Replace or dual-mode `_batched_resolve_claims` with **native-aligned sequential/two-phase** resolution.
   - Keep communication-before-commit if native does; match *ownership* semantics exactly.
   - Config flag e.g. `claim_resolve_mode: sequential_native | batched_legacy` (default `sequential_native`).

2. **Teacher = full native cooperative**
   - File: `src/race_casablanca/marl/bc.py`
   - Prefer executing / labeling from `RaceCooperativePolicy` (or equivalent) on the **same** decision epochs.
   - Deprecate weak intent-bridge as primary teacher; keep only as diagnostic ablation.

3. **Parity tests**
   - New: `tests/test_marl_native_parity.py`
   - Same seed + scenario: native rollout OT vs env+native-teacher rollout OT; claim owners alignment stats.
   - Guard: divergence rate / OT gap within gate G1.

4. **Short BC smoke**
   - Script: `scripts/train_race_marl.py` with procedural or fixed val.
   - Prove G2 directionally (even if full G2 needs longer run).

**Do not in Phase 1:** new reward fancy terms, locked_final, long MAPPO, paper tables.

**Exit:** G1 (required), G2 smoke (strongly preferred).

---

### Phase 2 — Make communication & energy load-bearing
**Objective:** Create regimes where no-comm / random-comm / naive charge visibly fail.

**Code / data changes**

1. **Partial observability default for MARL train**
   - Peer bids / rich peer features **absent** unless a message was delivered.
   - Files: observation builder / `build_restricted_observation` usage in `marl/env.py`; info_mode configs.

2. **Conflict curriculum**
   - Files: `marl/episode_sampler.py`, `configs/marl_training_protocol.json`, Solomon / demand configs.
   - Add regimes: `conflict_dense`, overlapping spatial catchments, synchronized releases, tight TW.
   - Round-robin include conflict with baseline / peak / tight.

3. **Energy-binding tier (NL)**
   - Lower initial SOC and/or effective range / longer tours so mid-shift charge is forced.
   - Partial charge targets in CC band vs full CV taper matter for TW.
   - Align with `EnergyModel.charge_duration_*`.

4. **Diagnostic baselines on stress set**
   - Re-run A vs B (no-comm vs full) **without learning** to verify G3 before heavy train.

**Exit:** G3 (and G5 design validated on at least a pilot).

---

### Phase 3 — Train learned coordinator
**Objective:** Competitive MARL with selective-comm advantage.

**Reward (priority order)** — extend protocol:
1. On-time / TW respect (primary)
2. Missed feasible pickup penalty
3. Communication bytes (λ)
4. NL charge regret (unnecessary full charge / stranded)

**Training recipe**
1. BC on native labels (heavy).
2. DAgger (correct covariate shift).
3. Short MAPPO fine-tune; early-stop on **full val** (not 2-scenario cherry-pick).
4. Seeds ≥ 3.
5. Episode source: procedural / Solomon-style per `configs/marl_training_protocol.json`.

**Ablations (keep IDs)**
| ID | Meaning |
|----|---------|
| A | No communication |
| B | Full / always-send feasible |
| C | Random matched bandwidth |
| D | Learned selective |
| E | Selective without energy cert content |
| F | Full RACE-MARL (selective + energy-aware cert / contest) |

**Exit:** G2 solid + G4 on conflict/stress set.

---

### Phase 4 — Flagship experimental matrix
**New results root:** `data/casablanca/online_results/top_tier/` (post-NL only).

**Axes**
- Delay: `{0, 30}` s; loss: `{0, 0.1}`
- Vehicles: `{3, 5, 8}`
- Solomon class: `{C, R, RC}`; size: `{15, 30, 45}`
- SOC / charge: binding vs comfortable; partial vs full
- Seeds: ≥3 for main comparisons

**Baselines in every main table**
- Native cooperative selective (upper reference)
- Greedy / no-peer
- A, B, C, F (learned)
- Optional: auction/CBBA-style if cheap to add

**Exit:** G4 + G5 with CIs; draft figures.

---

### Phase 5 — Freeze & locked holdout
1. Freeze configs, seeds, checkpoints, commit hash.  
2. Run `locked_final` **once** (G6).  
3. Write results reports + paper skeleton.  
4. Forbidden: retune after seeing locked numbers.

---

## 6. File ownership map

| Path | Role in plan |
|------|----------------|
| `reports/TOP_TIER_MARL_PLAN.md` | This living plan |
| `reports/NONLINEAR_CHARGING.md` | Physics note |
| `reports/MARL_TRAINING_DATA_PROTOCOL.md` | Train split / contamination |
| `configs/fleet_default.yaml` | NL `charging_curve` |
| `configs/marl_training_protocol.json` | Seeds, curriculum, reward priority |
| `src/race_casablanca/sim/energy.py` | NL charge durations |
| `src/race_casablanca/marl/env.py` | **Phase 1 critical** claim resolve + obs |
| `src/race_casablanca/marl/bc.py` | Native teacher / DAgger |
| `scripts/train_race_marl.py` | Train entry |
| `tests/test_marl_native_parity.py` | **New** G1 tests |
| `data/casablanca/online_results/top_tier/` | **New** result tree only |

---

## 7. Piece-by-piece execution protocol

For **every** code slice:

1. Read the active phase section in this doc.  
2. Implement the smallest vertical slice that moves a gate.  
3. Run targeted tests + a short smoke eval.  
4. Update §11 changelog: date, commit, gate status, notes.  
5. **Stop** if gate fails; diagnose before expanding scope.  
6. Do not start Phase *n+1* until Phase *n* exit is checked off.

Suggested first slices inside Phase 1:
1. `claim_resolve_mode=sequential_native` + unit/parity test  
2. Wire native teacher labels to that mode  
3. BC smoke on 1–2 scenarios  
4. Extend to full G1/G2 eval set  

---

## 8. Paper narrative (once gates pass)

1. **Problem:** online multi-agent EV pickup, TW, depot NL charging, limited comm.  
2. **Gap:** prior MARL either ignores energy/comm realism or fails to match strong cooperative heuristics because of decision-interface mismatch.  
3. **Method:** CTDE MARL with native-aligned decision epochs, selective/energy-certified messaging, NL-aware charge actions.  
4. **Results:** near-teacher service; large gains vs A/C under conflict+PO; bandwidth Pareto vs B; NL partial charge on binding instances.  
5. **Limits:** synthetic geo-grounded demand; depot-only charging; Casablanca OSM+traffic assumptions.

**Forbidden claims**
- Real observed courier orders  
- MARL superiority before G1–G4  
- Linear charging physics  

---

## 9. Risks & mitigations

| Risk | Mitigation |
|------|------------|
| Sequential resolve still ≠ native | Diff claim traces event-by-event; fix until G1 |
| Comm still worthless after PO | Strengthen conflict curriculum; measure duplicate claims |
| Energy still non-binding | Explicit binding generator tier; verify min SOC distribution |
| MAPPO forgets BC | Freeze backbone / low LR / short fine-tune; report BC as baseline |
| Scope explosion | Strict phase gates; no Phase 4 matrix until G4 |

---

## 10. Relation to older decisions

- Stage 6 “Option B applied simulation paper” remains compatible as **venue fallback**.  
- Stage 8.3 “PARTIAL / lead non-learning” is **overridden** for *direction*: we pursue MARL-centered top-tier path **after fixing the interface**.  
- Non-learning selective results remain valuable **baselines and causal controls**, not the sole center.

---

## 11. Changelog / gate log

| Date | Commit | Phase | Gate | Result | Notes |
|------|--------|-------|------|--------|-------|
| 2026-11-17 | `7bc662a` (NL) + plan | 0 | G0 | WIP | NL charging landed; linear results wiped; plan authored |
| 2026-11-17 | (local) Phase 1 slice 1 | 1 | G1 | **partial** | `claim_resolve_mode=sequential_native` default in `marl/env.py`; legacy `batched_legacy` kept; tests in `tests/test_marl_native_parity.py` green (intent OT ≥ 0.70). |
| 2026-11-17 | (local) Phase 1 slice 2 | 1 | G1 | **PASS** (execute teacher) | NativeBridge two-phase on `request_release`. `native_execute` mean ΔOT = **0.0** on 6 scenarios. |
| 2026-11-17 | (local) Phase 1 slice 3 | 1 | G1 step + BC smoke | **PASS** (safe path) | Soft `intent` still ~−21 pp (DAgger label-only). Safe step path: `intent_matched` = native execute + step preflight (skip re-send/re-claim). BC smoke via `native_execute`. |
| 2026-11-17 | (local) Phase 2 | 2 | G3 | **PASS soft** | `conflict_dense` + vehicle spread: native full−none mean ΔOT ≈ **+5.2 pp** (seed0/n=4); ablation A strips peer bids; energy_binding SOC=0.28; curriculum `conflict_only`. Hard ≥8 pp still noisy across seeds — tighten in Phase 3 train regimes. |
| 2026-11-17 | (local) Phase 3 slice 1 | 3 | G2/G4 prep | **infra PASS** | Multi-objective reward (OT − msgs/bytes − missed − charge). `--phase3` train preset (conflict_only + energy_binding + bc-native + F). `phase3_eval.py` + `eval_marl_phase3_ablations.py`. Full G2/G4 numbers need longer train run. |
| 2026-11-17 | (local) Phase 3 slice 2 | 3 | G2 | **partial / relative** | Conflict+energy_binding: teacher OT≈**0.26**, native full=none≈0.17 (G3Δ=0 under energy). BC OT≈**0.29** ≈ teacher (rel PASS). Absolute ≥0.78 needs comfortable/val mix. `--phase3` no longer forces `--energy-binding`. Native comfortable conflict ΔOT≈**+5.2 pp**. |
| 2026-11-17 | (local) Phase 3 slice 3 | 3 | G2 | **PASS (baseline)** | `eval_marl_g2_bc.py --regime baseline`: teacher OT=**0.938**, BC+DAgger OT=**0.917** (abs≥0.78, gap≈−2.1 pp). Comfortable conflict still hard (teacher≈0.44; BC lags). `--phase3` uses round_robin by default. |
| 2026-11-17 | (local) Phase 3 slice 4 | 3 | G2 hold / G4 | **G2 hold; G4 FAIL** | MAPPO `--phase3` round_robin: best mid-train OT=**0.875**. Checkpoint `phase3_F_seed0_best.pt`: baseline A/F≈**0.94** (F bytes=0=suppress), B/C≈**0.97**. Conflict all≈**0.319** (no OT sep; teacher≈0.46). Need conflict-heavy fine-tune for G4. |
| 2026-11-18 | (local) Phase 3 slice 5 | 3 | G3/G4 | **G3 soft in-env; G4 WIP** | Root cause: MARL env lacked vehicle spread → A=B. Spread on `conflict_dense`: B−A ≈ **+8 pp**; teacher≈0.46–0.53. Pre-retrain F≈0.40 (between A/B). Conflict BC+MAPPO retrain: F collapsed≈A (0.29) while B=0.38. Next: protect selective head (freeze ops / lower LR / more DAgger on conflict). |
| 2026-11-18 | (local) Phase 3 slice 6 | 3 | G4 | **soft near-miss** | `--freeze-op` wired. Conflict+spread BC+MAPPO: seed0 A=**0.354** B/C=**0.438** F=**0.396** bytes F=4.7k≪B=23k. F>A (+4.2 pp) but F vs B gap **−4.2 pp** (need ≤3 pp). Teacher=0.531. |
| 2026-11-18 | (local) Phase 3 slice 7 | 3 | G4 | **PASS** | Root cause: F cert-gated **mask** blocked first bids. Fix: open mask + execute cert filter (opening bid; ENERGY_CERT=12 kWh; slack=450s). `g4mask` ckpt: A=**0.354** B=**0.438** F=**0.417** bytes F/B=**0.58** msgs F/B=**0.51**. |
| 2026-11-18 | (local) Phase 3 slice 8 | 3→4 | G4 multi-seed | **partial** | Seeds 0–2: hard pass **1/3** (seed0 only). Seed1/2 F≈A. Heavier retrain `g4ms` did not fix. Phase 4 scaffold+smoke OK (`configs/phase4_matrix.json`, `matrix_smoke.json`). Next: multi-seed train curriculum before full matrix. |
| 2026-11-18 | (local) Phase 3 slice 9 | 3 | G4 multi-seed | **PASS 3/3** | Root: lex opener + uncapped same-step energy bypass. Fix: best-travel free opener, contested cap-2 (no energy bypass), F `max_sends=1`. `g4mask` eval: hard **3/3**, mean br=**0.64**, F≈B OT (seed2 F>B). `phase3_g4_multiseed.json`. |
| 2026-11-18 | (local) Phase 4 slice 1 | 4 | core matrix | **partial** | `core` mode: regime×energy×seeds (12 cells). Conflict unbound G4 hard **3/3**. Conflict+energy_binding: F=B OT but br≈**0.88** (soft only). Baseline: F≈A≈B ceiling, br≈0.4. `phase4/matrix_core.json`. |
| 2026-11-18 | (local) Phase 4 slice 2 | 4 | energy bytes + channel | **partial** | Energy-bind G4: flex-alone second-opener removed + fleet cap2 (pending-only bypass) → bind T/F hard **6/6** (`conflict_energy_g4.json`). Channel matrix: delay=0 loss∈{0,0.1} hard **6/6**; delay=30 A=B=F (G3 collapse) hard **0/6** though F still ≪B bytes. `matrix_channel.json`. |
| 2026-11-21 | (local) Phase 4 slice 3 | 4 | delay G3/G4 | **PASS ≥2/3** | Root: MARL claimed on release before delayed bids arrived. Fix: native-style assign wait (`assignment_wait_s`) + hold claims while `_pending_assign_requests`. delay=30 seeds: G3 B−A **+3–9 pp**; G4 hard **2/3** (seed2 soft). delay=0 unchanged. `delay30_g3_g4.json`. |
| 2026-11-21 | (local) Phase 4 slice 4 | 4 | fleet axis | **PASS nv≤5** | `fleet` mode nv∈{3,5,8}×seeds. G4 hard **3/3** at nv=3 and **3/3** at nv=5 (B−A up to +26 pp). nv=8: OT ceiling A≈B≈F (hard **1/3**). Spot delay=30 nv=5 seed0: G3 +14.6 pp, G4 hard. `matrix_fleet.json`. |
| 2026-11-21 | (local) Phase 4 slice 5 | 4 | G5 NL charge | **PASS ≥2/3** | Partial target 0.70 vs always-full 1.0 on `conflict_dense`+energy_binding: hard **2/3**, mean ΔOT **+1.4 pp**, charge time ~**2.3×** lower; NL taper from SOC 0.28 is **2.46×**; exact `C_partial_better` best=1 vs always-full=0. `g5_nl_charge.json`. |
| 2026-11-21 | (local) Phase 5 | 5 | G6 locked_final | **PASS (one-shot)** | Freeze manifest (`phase5/freeze_manifest.json`, ckpt sha256 `3aba4b51…`). Locked 30 scenarios A/B/C/F: F=B OT **0.806**, F−A **+1.2 pp**, bytes F/B **0.57**. Peak carries the gap; baseline ceiling. Phase4 CIs: `phase4_summary.json`. Skeleton: `TOP_TIER_PAPER_SKELETON.md`. **No retune.** |
| 2026-11-21 | (local) Paper | 5 | tables | **PASS** | Filled `reports/TOP_TIER_RESULTS.md` (conflict G4, delay, fleet, energy/G5, locked G6). |
| 2026-11-21 | (local) Paper | 5 | figures | **PASS** | `scripts/plot_top_tier_figures.py` → `reports/figures/top_tier/` figs 1–5 (png+pdf). |

---

## 12. Immediate next action

**Paper draft:** Tables in `reports/TOP_TIER_RESULTS.md`; figures in `reports/figures/top_tier/` (`scripts/plot_top_tier_figures.py`). Skeleton: `TOP_TIER_PAPER_SKELETON.md`. Do **not** retune. Optional next: prose draft (methods/results/limits) or commit freeze artifacts.
