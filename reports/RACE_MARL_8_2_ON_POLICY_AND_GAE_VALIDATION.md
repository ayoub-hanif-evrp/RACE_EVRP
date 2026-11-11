# RACE-MARL Stage 8.2 — On-Policy Likelihood & GAE Validation

## External communication treatments (B / C)

For `B_full_comm` and `C_random_matched`:

- The environment **overrides** the sampled communication action.
- `info["executed_comm"]` stores the action that actually ran.
- `info["comm_learnable"]=False` marks the step as externally controlled.
- `MAPPOTrainer.collect` stores executed actions and zeros communication log-prob when not learnable.
- `MAPPOTrainer.update` multiplies communication likelihood / entropy by `comm_learnable`, so forced/random messaging contributes **no** communication-policy gradient.

Operational head remains trainable under identical routing/charging capabilities.

Unit test: `test_external_comm_produces_no_comm_head_gradient` asserts `comm_learnable_frac=0` and `comm_head` gradient norm \< 1e-6 under B.

Do **not** label C as a learned communication policy; it is a matched-budget random control.

## GAE episode boundaries

`compute_gae_time` now cuts the advantage chain when `max(dones[t], truncs[t]) = 1`:

- Natural terminal: `dones=1`, no bootstrap into the next stored step.
- Administrative / budget truncation: `truncs=1`; mid-buffer reset does not bootstrap from the next episode’s value.
- Buffer-end mid-episode truncation: bootstrap via `last_value`.

Deterministic two-episode test: `test_gae_cuts_across_episode_reset_boundary` — reward 100 in episode 2 does not inflate episode 1 advantage (natural done **or** trunc boundary).

## Matched random budget

`matched_send_p` is calibrated **once** from the cooperative selective teacher’s send rate on training scenarios and written to `stage82_matched_send_p.json` before learned runs. C uses this predeclared probability; it is not chosen post-hoc per test scenario.

## Weak-test cleanup

Vacuous assertions (`or True`, bare `>= 0` OT checks) in MARL tests were replaced with exact expectations for claims, sends, reward–metric equality, and BC accuracy floors. See `tests/test_marl_factorized_actions.py`, `test_marl_reward_accounting.py`, `test_marl_training_generalization.py`, `test_marl_message_causality.py`.
