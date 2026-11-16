# FINAL COMMUNICATION ACCOUNTING

## Semantics (Prompt 2 correction)

`OnlineSimulator.broadcast_task_bid` counts **per recipient destination**.

| Counter | Meaning |
|---------|---------|
| `n_bid_attempted_messages/bytes` | Sender attempts, **including** frames later dropped |
| `n_bid_dropped_messages/bytes` | Network drops before bus schedule |
| `n_bid_scheduled_*` / legacy `n_bid_messages`/`n_bid_bytes` | Successfully scheduled (historical pre-Prompt-2) |
| `n_bid_delivered_*` | Recipient ingest |
| `n_bid_delivers_superseded` | Newer delayed bid replaces pending deliver (not a drop) |
| `n_bid_delivers_coalesced` | Skipped superseded deliver events |

**Primary paper cost:** attempted recipient bytes.

## Tests

`tests/test_prompt2_metrics_accounting.py`:

- 0% loss: attempted = scheduled = delivered (zero delay)  
- 10%: attempted ≥ delivered; dropped = attempted − scheduled  
- 100%: attempted > 0, delivered = 0, legacy scheduled = 0, no deadlock, exclusive ownership  

## Development results

Selective/CSC-lite @0 s ≈ 55.8 kB attempted mean; full ≈ 220 kB (−74.6%).  
Under 10% loss @30 s, H still ≡ I on OT/owners while attempted bytes remain positive.
