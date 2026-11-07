"""Baseline C — restricted-information cooperative dispatch.

Uses only own state, delivered peer snapshots, and public announcements.
Task ownership uses the central registry (not fully decentralized).
"""

from __future__ import annotations

from race_casablanca.sim.policy_api import ActionInterface, FullInfoObservation, RestrictedObservation


class LimitedInfoCooperativePolicy:
    name = "limited_info_cooperative"

    def __init__(self, broadcast_period_s: float = 120.0):
        self.broadcast_period_s = broadcast_period_s
        self._last_broadcast_s: dict[str, float] = {}

    def on_decision(
        self,
        obs: FullInfoObservation | RestrictedObservation,
        actions: ActionInterface,
        reason: str,
    ) -> None:
        if isinstance(obs, FullInfoObservation):
            # If mistakenly invoked in full mode, act only for each vehicle via restriction
            # by refusing — experiments must set info_mode=restricted.
            return
        assert isinstance(obs, RestrictedObservation)
        vid = obs.vehicle_id

        if reason != "message":
            last = self._last_broadcast_s.get(vid, -1e18)
            if obs.now_s - last >= self.broadcast_period_s:
                actions.broadcast_own_state(vid)
                self._last_broadcast_s[vid] = obs.now_s

        # Defer if a peer snapshot (stale) looks clearly better for a task
        announced = sorted(obs.announced, key=lambda t: t.tw_end_s)
        self_load = len(obs.own_committed)
        for task in announced:
            # Skip claiming if a fresher peer message says they have fewer commitments
            defer = False
            for peer in obs.peers.values():
                if len(peer.committed) < self_load:
                    defer = True
                    break
            if defer and self_load > 0:
                continue

            chk = actions.check_insertion(vid, task.request_id)
            if not chk.feasible:
                if task.tw_end_s <= obs.now_s:
                    actions.reject_request(task.request_id)
                continue
            if actions.claim_task(vid, task.request_id):
                break
