# RACE-MARL — Environment validation

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
