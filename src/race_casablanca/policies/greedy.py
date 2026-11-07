"""Baseline A — online feasibility-aware greedy insertion (full information)."""

from __future__ import annotations

from race_casablanca.sim.policy_api import ActionInterface, FullInfoObservation, RestrictedObservation


class GreedyInsertionPolicy:
    name = "greedy_insertion"

    def on_decision(
        self,
        obs: FullInfoObservation | RestrictedObservation,
        actions: ActionInterface,
        reason: str,
    ) -> None:
        if not isinstance(obs, FullInfoObservation):
            # Full-info greedy should not run under restricted observations.
            return
        available = sorted(obs.available, key=lambda t: t.tw_end_s)
        for task in available:
            best_v = None
            best_cost = None
            for vid in obs.vehicles:
                chk = actions.check_insertion(vid, task.request_id)
                if not chk.feasible:
                    continue
                if best_cost is None or chk.added_travel_s < best_cost:
                    best_cost = chk.added_travel_s
                    best_v = vid
            if best_v is None:
                if task.tw_end_s <= obs.now_s:
                    actions.reject_request(task.request_id)
                continue
            actions.claim_task(best_v, task.request_id)
