# Wait × Peer-Info Factorial (60 development scenarios)

**Artifacts:** `race_trust_factorial.csv`, `race_trust_factorial_summary.json`  
**Not** locked_final. Historical closeout CSVs preserved.

## Arms

| Label | Timing | Peer use |
|-------|--------|----------|
| NONE_NOW | immediate | none |
| NONE_MATCHED_WAIT | H deadline-energy wait, no msgs | none |
| H_NO_PEER | H wait + selective msgs | ignore peers at claim |
| H_CURRENT | H wait | broken `delay_half` trust |
| H_VALID_PEER | H wait | repaired `ttl_commitment` |
| SELECTIVE_LEGACY | legacy 1.25×delay wait | TTL freshness |
| FULL_VALID_PEER | H wait + full send | `ttl_commitment` |

## Means (selected)

### Delay 30 s

| Treatment | Mean OT | Bytes | Wait | Defers | Trusted | Untrusted |
|-----------|--------:|------:|-----:|-------:|--------:|----------:|
| NONE_NOW | **0.8361** | 0 | 0 | 0 | 0 | 0 |
| NONE_MATCHED_WAIT | 0.8353 | 0 | 24.6 | 0 | 0 | 0 |
| H_NO_PEER | 0.8353 | 59156 | 24.6 | 0 | 22.0 | 0.1 |
| **H_CURRENT** | **0.8353** | 59156 | 24.6 | **0** | **0** | **22.1** |
| H_VALID_PEER | 0.7731 | 217979 | 23.9 | 40.8 | 85.5 | 9.0 |
| SELECTIVE_LEGACY | 0.7643 | 254757 | 37.5 | 45.1 | 100.3 | 1.9 |

### Delay 120 s

H_CURRENT = H_NO_PEER = H_VALID_PEER = NONE_MATCHED_WAIT = **0.8318** OT (wait ≈49 s < 120 s delay → peers rarely usable before assign). NONE_NOW = 0.8361. SELECTIVE_LEGACY = 0.7974.

## Decisive questions

| Q | Result (60 ep) |
|---|----------------|
| **A.** H_CURRENT ≡ H_NO_PEER at 30/120? | **YES** — dOT=0, 60/60 identical owners |
| **B.** H_CURRENT better than NONE_MATCHED_WAIT? | **NO** — identical OT and owners; msgs add bytes only |
| **C.** H_VALID_PEER improves vs no-peer? | **NO** — at 30s **−6.22 pp** (CI −8.6 to −3.9); at 120s tied |
| **D.** Source of H_CURRENT vs legacy selective gains? | **Shorter wait + ignoring delayed peers**, not useful peer info |
| **E.** Energy/travel features change wait? | Yes — wait uses real `check_insertion` travel; shared wait across H_* / NONE_MATCHED_WAIT |

## Attribution

```text
H_CURRENT delay OT  ≈  NONE_MATCHED_WAIT  ≈  H_NO_PEER
H_VALID_PEER (trusting delayed peers)  worsens  OT at 30s
NONE_NOW  remains  best / tied-best  under delay
```
