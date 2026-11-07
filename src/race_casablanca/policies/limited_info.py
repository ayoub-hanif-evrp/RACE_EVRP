"""Restricted-information cooperative dispatch with configurable communication.

Same claim rule for all modes; only messaging differs:
- none: no voluntary peer-state broadcasts
- periodic: relies on simulator PERIODIC_BROADCAST clock (no opportunistic sends)
- decision_triggered: send only when estimated decision value exceeds threshold
"""

from __future__ import annotations

from dataclasses import replace

from race_casablanca.policies.restricted_dispatch import intended_claim_id, restricted_claim_pass
from race_casablanca.sim.policy_api import ActionInterface, FullInfoObservation, RestrictedObservation


class LimitedInfoCooperativePolicy:
    name = "limited_info_cooperative"

    def __init__(
        self,
        comm_mode: str = "periodic",  # none | periodic | decision_triggered
        value_threshold: float = 120.0,  # seconds of estimated travel penalty
        broadcast_period_s: float | None = None,  # legacy alias → periodic mode
    ):
        if broadcast_period_s is not None and comm_mode == "periodic":
            # Period itself is configured on SimConfig.periodic_broadcast_s
            pass
        self.comm_mode = comm_mode
        self.value_threshold = value_threshold
        self.n_messages_sent_by_policy = 0
        # Invocations triggered by a delivered peer message (not usefulness)
        self.n_message_driven_decision_invocations = 0
        # Counterfactual: intended claim differs with vs without peer snapshots
        self.n_counterfactual_decision_changes = 0
        # Deprecated alias retained for old scripts; equals counterfactual changes
        self.n_decision_changing_messages = 0

    def on_decision(
        self,
        obs: FullInfoObservation | RestrictedObservation,
        actions: ActionInterface,
        reason: str,
    ) -> None:
        if not isinstance(obs, RestrictedObservation):
            return
        vid = obs.vehicle_id

        if self.comm_mode == "periodic":
            # Broadcasts are driven by PERIODIC_BROADCAST events only.
            pass
        elif self.comm_mode == "decision_triggered" and reason != "message":
            if self._should_send(obs):
                actions.broadcast_own_state(vid)
                self.n_messages_sent_by_policy += 1
        # comm_mode == "none": never voluntary broadcast

        if reason == "message":
            self.n_message_driven_decision_invocations += 1
            with_peers = intended_claim_id(obs, actions)
            empty = replace(obs, peers={})
            without_peers = intended_claim_id(empty, actions)
            if with_peers != without_peers:
                self.n_counterfactual_decision_changes += 1
                self.n_decision_changing_messages += 1

        restricted_claim_pass(obs, actions)

    def _should_send(self, obs: RestrictedObservation) -> bool:
        """Send if own commitment load or battery tightness may change peer claims.

        Uses only own visible state (no privileged peer truth).
        """

        v = obs.self_state
        load_pressure = 60.0 * len(v.committed)
        reserve_like = 0.15 * 40.0
        headroom = max(0.0, v.battery_kwh - reserve_like)
        energy_pressure = 300.0 / (1.0 + headroom) if v.battery_kwh < 20.0 else 0.0
        announce_pressure = 40.0 * min(3, len(obs.announced)) if not v.busy else 20.0 * min(2, len(obs.announced))
        value = load_pressure + energy_pressure + announce_pressure
        return value >= self.value_threshold
