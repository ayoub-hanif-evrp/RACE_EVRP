# FINAL METHOD DECISION — Prompt 1/5

**Scientific classification: PARTIAL**

**Date:** 2026-11-15  
**Pilot unit:** 6 Casablanca train scenarios (baseline / peak / tight), 3 EVs, SOC 0.35  
**Locked-final used:** No

---

## Selected methodology for Prompt 2

**Name:** RACE-COMM Selective with commitment-safe claim (CSC-lite)

**Frozen configuration**

| Parameter | Value |
|-----------|-------|
| `comm_mode` | `selective` |
| `claim_mode` | `csc` |
| `send_claim_signals` | `False` |
| `assign_wait_mode` | `deadline_energy` |
| `peer_trust_mode` | `ttl_commitment` |
| `wait_authority` | `decentralized_signal` |
| `fair_physical_decisions` | `True` |
| `max_assign_wait_s` | `60` |

**Operational rule (one sentence):** Rank with peer *offers* only under near-zero delay; under positive message delay, do **not** defer a feasible local claim to a nonbinding peer offer — defer only to fresh `claim_intent` / `owned` signals if present (confirmation messaging disabled in the frozen config).

---

## Why PARTIAL (not PASS)

1. **Correctness Gate 1 — PASS.** Exclusive ownership, bounded waits, information-boundary fixes, and adversarial tests A–L pass.
2. **Multi-agent Gate 2 — PARTIAL.** At delay = 0, peer offers change ownership vs no-peer (+0.97 pp OT, owner Hamming 9.17 / 6 scenarios). Under delay ≥ 15 s, counterfactual claim changes and owner Hamming vs `MATCHED_WAIT_NO_PEER` are **zero** — delivered offers are intentionally ignored.
3. **Performance Gate 3 — PARTIAL.** CSC with confirmation (`G`) matches no-peer service under delay but **adds ~44 kB** with **0 OT gain** vs `H` / `E`. Speculative-deferral selective (`D`/`F`) loses **11–16 pp** OT at 15–30 s; beating that broken baseline is **not** sufficient for PASS.
4. **Novelty Gate 4 — PARTIAL / narrow.** Distinguishing nonbinding offers from commitments under delay is technically precise for this EV simulator, but is close to deadline-aware auction + timeout practice; claim-intent confirmation did not earn its keep.
5. **Integrity Gate 5 — PASS.** Results reproducible; no locked-final; no fabricated wins.

---

## Rejected alternatives

| Candidate | Reason rejected |
|-----------|-----------------|
| `G_FINAL_CANDIDATE` (CSC + claim_intent/owned) | Same OT as `H` under all delays; extra confirmation bytes unused |
| Legacy / current selective offer-ranking under delay (`C`/`D`/`F`) | Speculative deferral destroys service (−11 to −16 pp at 15–30 s) |
| Full bidding under delay (`B`) | Same failure mode; far higher bytes |
| Pure `NONE_NOW` | Loses the +0.97 pp zero-delay peer-offer gain; still a strong delay reference |
| RACE-ECOM certificates | Prior PASS-1: PROVED≈0; not restarted |
| MARL / GNN | Prior negative; out of scope |

---

## What Prompt 2 must verify

On the expanded development ensemble (not locked-final):

1. Zero-delay selective+CSC-lite vs none (service–bytes Pareto).
2. Delayed regimes: CSC-lite ≡ matched no-peer service (null multi-agent effect under delay is a **finding**, not a bug).
3. Communication efficiency vs full bidding at delay = 0.
4. Honest reporting that delayed peer *offers* are nonbinding and currently unused for ranking.
