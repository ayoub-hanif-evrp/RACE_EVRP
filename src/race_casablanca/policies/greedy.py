"""Baseline A — online feasibility-aware greedy insertion (full information)."""

from __future__ import annotations

from race_casablanca.sim.environment import OnlineSimulator


class GreedyInsertionPolicy:
    name = "greedy_insertion"

    def on_decision(self, sim: OnlineSimulator, reason: str) -> None:
        if sim.config.info_mode != "full":
            # Still works from global available list; used only in full mode experiments.
            pass
        available = list(sim.available_requests())
        # Process by urgency (earliest deadline first)
        available.sort(key=lambda r: r.tw_end_s)
        for req in available:
            best_v = None
            best_cost = None
            for vid in sim.vehicles:
                chk = sim.check_insertion(vid, req.request_id)
                if not chk.feasible:
                    continue
                if best_cost is None or chk.added_travel_s < best_cost:
                    best_cost = chk.added_travel_s
                    best_v = vid
            if best_v is None:
                # Leave available; may expire later. Do not reject early unless past deadline.
                if req.tw_end_s <= sim.now_s:
                    sim.reject_request(req.request_id)
                continue
            sim.try_assign(best_v, req.request_id)
