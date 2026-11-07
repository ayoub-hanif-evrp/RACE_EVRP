"""Baseline C — limited-information cooperative dispatch.

Each vehicle claims tasks using own state + delayed peer updates.
Task ownership uses the central registry (not fully decentralized).
"""

from __future__ import annotations

from race_casablanca.sim.environment import OnlineSimulator


class LimitedInfoCooperativePolicy:
    name = "limited_info_cooperative"

    def __init__(self, broadcast_period_s: float = 120.0):
        self.broadcast_period_s = broadcast_period_s
        self._last_broadcast_s = -1e18

    def on_decision(self, sim: OnlineSimulator, reason: str) -> None:
        # Periodic state exchange — never from message delivery (avoids feedback storms).
        if reason != "message" and sim.now_s - self._last_broadcast_s >= self.broadcast_period_s:
            for vid in sim.vehicles:
                sim.broadcast_state(vid)
            self._last_broadcast_s = sim.now_s

        available = list(sim.available_requests())
        available.sort(key=lambda r: r.tw_end_s)

        for req in available:
            # Rank idle-ish vehicles by travel time from their *known* position.
            # In restricted mode we still use true own state for the acting vehicle;
            # peers only affect tie-breaking via stale views.
            candidates: list[tuple[float, str]] = []
            for vid, v in sim.vehicles.items():
                if v.busy and len(v.committed) >= 3:
                    continue
                chk = sim.check_insertion(vid, req.request_id)
                if not chk.feasible:
                    continue
                # Penalty if peer stale view suggests peer is closer (coordination heuristic)
                peer_penalty = 0.0
                for peer, view in sim.local_views.get(vid, {}).items():
                    if peer == vid:
                        continue
                    # If a peer announced fewer commitments and higher battery, defer slightly
                    if len(view.get("committed", [])) < len(v.committed):
                        peer_penalty += 30.0
                candidates.append((chk.added_travel_s + peer_penalty, vid))
            if not candidates:
                if req.tw_end_s <= sim.now_s:
                    sim.reject_request(req.request_id)
                continue
            candidates.sort()
            # First feasible claim wins via registry (duplicate claims rejected)
            for _cost, vid in candidates:
                if sim.try_assign(vid, req.request_id):
                    break
