# Stage 3B — Method validation

Parent commit at experiment time: `dfb1b24` (Stage 3A). Code and results for this stage are committed after these runs.

## Correctness preflight (Task 1)

| Check | Result |
| --- | --- |
| Partial `commit_fleet_plans` leaves omitted vehicles untouched | Pass (`tests/test_stage3b_race.py`) |
| Full-fleet commit can clear editable plans when all vehicles listed | Pass |
| Message usefulness uses counterfactual claim comparison | Pass; `n_message_driven_decision_invocations` ≠ usefulness; `n_counterfactual_decision_changes` only when intended claim differs |
| Hidden realized energy not used in planning | Still covered by Stage 3A tests |
| Claim counters single-sourced | Still covered by Stage 3A / greedy integrity |

Frozen dataset `casablanca_release_v1` unchanged.

## RACE prototype behavior

- Policy: `src/race_casablanca/policies/race_commitment.py`
- Hard gate identical to baselines (conservative energy + windows + payload + depot reserve)
- Soft score: state-dependent \(\mu_E,\mu_T\) on residual \(\Phi_E,\Phi_T\) loss
- Ablation: `use_opportunity_cost=False` → min travel among feasible (plus same charge heuristic)
- Optional scarcity-triggered reassignment when energy flex is low

Synthetic ablation: RACE without opportunity cost matches greedy served count on the line toy scenario.

## Safety

Across all Stage 3B Casablanca training runs: **0** battery reserve violations and **0** emergency strandings under the documented disturbance model.
