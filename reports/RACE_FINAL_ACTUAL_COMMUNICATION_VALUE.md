# Actual Communication Value

## Classification of H_CURRENT

**Primary: Safe fallback under delayed communication + deadline-aware commitment scheduling.**  
**Not: Communication-efficient multi-agent cooperation that exploits delayed peer bids.**

Evidence:

1. Trust horizon audit: normally delivered bids age ≥ delay > 0.5×delay → rejected ([RACE_FINAL_TRUST_HORIZON_AUDIT.md](RACE_FINAL_TRUST_HORIZON_AUDIT.md)).
2. Factorial: H_CURRENT ownership and OT **identical** to H_NO_PEER and NONE_MATCHED_WAIT at 30/120 s (n=60).
3. H_VALID_PEER (repaired trust) **uses** peers (trusted≈85 at 30s) but **reduces** OT vs ignore-peers.

## Deterministic cases (`tests/test_communication_value_cases.py`)

| Case | Result |
|------|--------|
| 1. Valid delayed better peer | `ttl_commitment` defers; `delay_half` wrongly claims |
| 2. Withdrawn bid ignored | Own claims |
| 3. No peer | Immediate claim |
| 4. Infeasible own | No claim even if “nearest” travel |
| 5. Executed episode | H_CURRENT owners = H_NO_PEER under 30s delay |

## What communication *does* buy at delay 0

Selective / H_VALID_PEER / H_CURRENT match OT 0.8424 vs NONE_NOW 0.8361 (+0.63 pp mean; prior CIs often include 0). Bytes ~51.8 KB vs full ~202 KB. Event-triggered equals selective at delay 0 in closeout.

## Honest method label

| Claim | Supported? |
|-------|------------|
| Deadline-aware assign timing reduces delay harm vs legacy selective | **Yes** |
| Ignoring untrustworthy delayed bids prevents harmful deferral | **Yes** (but H_CURRENT ignores *all* delayed bids) |
| Useful delayed peer information improves fleet OT | **No** on this ensemble — trusting them hurt at 30s |
| Energy-aware wait uses local insertion | **Yes** (repaired) |
