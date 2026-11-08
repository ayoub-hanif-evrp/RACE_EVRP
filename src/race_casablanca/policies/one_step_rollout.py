"""Conventional one-step rollout baseline (same synthetic model / budget class).

Uses post-decision sample-average lookahead over claim actions only (no endogenous
charge candidates). Established anticipatory control — comparison reference, not
RACE novelty.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from race_casablanca.demand.synthetic_futures import SyntheticFutureModel
from race_casablanca.policies.race_postdecision import RacePostDecisionPolicy
from race_casablanca.sim.lookahead import CandidateAction
from race_casablanca.sim.policy_api import ActionInterface, FullInfoObservation, RestrictedObservation


@dataclass
class OneStepRolloutPolicy:
    """Claim-only sample-average rollout with reactive adaptive charging afterward."""

    name: str = "one_step_rollout"
    n_samples: int = 3
    n_synthetic_requests: int = 4
    max_claim_candidates: int = 8
    seed: int = 0
    future_model: SyntheticFutureModel | None = None
    decision_log: list[dict[str, Any]] = field(default_factory=list)
    total_lookahead_runtime_s: float = 0.0

    def on_decision(
        self,
        obs: FullInfoObservation | RestrictedObservation,
        actions: ActionInterface,
        reason: str,
    ) -> None:
        # Delegate to post-decision engine with charging candidates disabled
        inner = RacePostDecisionPolicy(
            name="one_step_rollout_inner",
            n_samples=self.n_samples,
            n_synthetic_requests=self.n_synthetic_requests,
            max_claim_candidates=self.max_claim_candidates,
            max_charge_candidates=0,
            enable_future_eval=True,
            enable_charge_actions=False,
            future_model=self.future_model,
            seed=self.seed,
        )
        inner.on_decision(obs, actions, reason)
        self.decision_log.extend(inner.decision_log)
        self.total_lookahead_runtime_s += inner.total_lookahead_runtime_s
        # Reactive adaptive charge after claim selection
        from race_casablanca.policies.charging_controller import ChargingController

        if isinstance(obs, FullInfoObservation):
            ChargingController(mode="adaptive_headroom").apply(actions._sim, actions)
