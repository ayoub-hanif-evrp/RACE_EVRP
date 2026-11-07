"""Baseline A — online feasibility-aware greedy insertion (full information)."""

from __future__ import annotations

from dataclasses import dataclass, field

from race_casablanca.policies.charging_controller import ChargingController
from race_casablanca.sim.policy_api import ActionInterface, FullInfoObservation, RestrictedObservation


@dataclass
class GreedyInsertionPolicy:
    name: str = "greedy_insertion"
    charging: ChargingController = field(
        default_factory=lambda: ChargingController(mode="adaptive_headroom")
    )

    def on_decision(
        self,
        obs: FullInfoObservation | RestrictedObservation,
        actions: ActionInterface,
        reason: str,
    ) -> None:
        if not isinstance(obs, FullInfoObservation):
            return
        available = sorted(obs.available, key=lambda t: t.tw_end_s)
        for task in available:
            best_v = None
            best_pos = None
            best_cost = None
            for vid in obs.vehicles:
                chk = actions.check_insertion(vid, task.request_id)
                if not chk.feasible:
                    continue
                cost = float(chk.marginal_travel_s)
                if best_cost is None or cost < best_cost:
                    best_cost = cost
                    best_v = vid
                    best_pos = chk.insert_position
            if best_v is None:
                if task.tw_end_s <= obs.now_s:
                    actions.reject_request(task.request_id)
                continue
            actions.claim_task(best_v, task.request_id, force_position=best_pos)
        self.charging.apply(actions._sim, actions)
