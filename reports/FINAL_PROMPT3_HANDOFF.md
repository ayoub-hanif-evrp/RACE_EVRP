# FINAL PROMPT 3 HANDOFF

## Prompt status

**COMPLETE**

## Frozen method (unchanged)

`RaceCooperativePolicy` CSC-lite parameters in `configs/final_frozen.json` / `configs/final_locked_manifest.json`.

## Version anchors

| Role | SHA / hash |
|---|---|
| CSC-lite implementation | `deb750af7edebdc8868eed2af6fa389e77765136` |
| Prompt 2 freeze metadata | `3e25c5458cb4799f521b63c537950eb702619084` |
| Prompt 3 push (this work) | `812839e963878700f54d9aa242ea8b21bbc2dda2` |
| Content hashes | `configs/final_locked_manifest.json` → `content_hashes` |

## Locked evaluation

- 720/720 OK; 0 failures
- Results dir: `data/casablanca/online_results/final_locked/`
- Figures: `reports/figures/final_locked/fig1`–`fig6`
- Stats: `final_locked_paired.json`, `FINAL_STATISTICAL_RESULTS.md`

## Headline locked numbers (mean OT)

| | 0 s | 30 s | 120 s |
|---|---:|---:|---:|
| H CSC-lite | 0.8342 | 0.8303 | 0.8197 |
| B Full | 0.8342 | 0.7506 | 0.8197 |
| A None | 0.8281 | 0.8281 | 0.8281 |
| I Matched wait 0-comm | 0.8281 | 0.8303 | 0.8197 |
| E Event-triggered | 0.8342 | — | — |

H vs B @0: ΔOT 0; bytes ratio 0.239.  
H vs A @0: +0.61 pp [−0.42, +1.64].  
H vs I @30/@120: exact equality.  
H vs E @0: exact equality (no distinct advantage).  
H vs G @30: +8.33 pp.

## Publication assessment

**Outcome B** — focused applied method + rigorous negative delayed-information result.

## Prompt 4 readiness

**YES** — write the journal manuscript from these frozen locked results. Do **not** retune CSC-lite, retrain MARL, or reopen locked_final as a development set.

## Reproduction

```text
# Preflight + locked matrix (resumable)
python scripts/run_race_prompt3_locked_final.py

# Analyze / figures (if re-run)
python scripts/run_race_prompt3_locked_final.py --analyze-only   # if supported
python scripts/_analyze_locked.py
```

Tests: `pytest tests/test_prompt3_baseline_fixes.py` (+ existing CSC/comm suites).

## Reports for Prompt 4

- `reports/FINAL_PREFLIGHT_CORRECTIONS.md`
- `reports/FINAL_LOCKED_RESULTS.md`
- `reports/FINAL_STATISTICAL_RESULTS.md`
- `reports/FINAL_DATASET_VALIDITY.md`
- `reports/FINAL_COMMUNICATION_RESULTS.md`
- `reports/FINAL_CAUSAL_FINDINGS.md`
- `reports/FINAL_OPERATIONAL_RESULTS.md`
- `reports/FINAL_PUBLICATION_EVIDENCE.md`
- `reports/FINAL_PROMPT3_HANDOFF.md`
