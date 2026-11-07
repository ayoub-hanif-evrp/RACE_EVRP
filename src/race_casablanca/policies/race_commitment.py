"""RACE — Risk-Aware Commitment and Energy management (Stage 3C).

Hard constraints: same conservative feasibility gate as baselines.
Soft ranking: minimize J(v,p) over ALL feasible vehicles and insertion positions.

Ablation flags are independent:
- use_flexibility_pricing
- allow_reassign
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from race_casablanca.policies.charging_controller import ChargingController
from race_casablanca.sim.feasibility_check import (
    editable_suffix,
    evaluate_insertion,
    projected_state_after_lock,
    simulate_plan_conservative,
)
from race_casablanca.sim.policy_api import ActionInterface, FullInfoObservation, RestrictedObservation
from race_casablanca.sim.types import RequestStatus


@dataclass
class RaceCommitmentPolicy:
    name: str = "race_commitment"
    use_flexibility_pricing: bool = True
    allow_reassign: bool = True
    # pricing mode: inverse_slack (default) | fixed_weight
    pricing_mode: str = "inverse_slack"
    alpha_energy: float = 240.0
    beta_time: float = 0.5
    # fixed-weight reference constants (seconds per kWh / dimensionless mix)
    fixed_mu_e: float = 120.0
    fixed_mu_t: float = 0.35
    e_typical_kwh: float = 2.0
    t_typical_s: float = 900.0
    eps: float = 0.25
    charging: ChargingController = field(
        default_factory=lambda: ChargingController(mode="adaptive_headroom")
    )
    decision_traces: list[dict[str, Any]] = field(default_factory=list)
    # Legacy alias used by Stage 3B scripts/tests
    use_opportunity_cost: bool | None = None

    def __post_init__(self) -> None:
        if self.use_opportunity_cost is not None:
            self.use_flexibility_pricing = bool(self.use_opportunity_cost)

    def on_decision(
        self,
        obs: FullInfoObservation | RestrictedObservation,
        actions: ActionInterface,
        reason: str,
    ) -> None:
        if isinstance(obs, RestrictedObservation):
            self._restricted_self_pass(obs, actions)
            self.charging.apply(actions._sim, actions)
            return
        if not isinstance(obs, FullInfoObservation):
            return
        if reason == "message":
            return

        sim = actions._sim
        available = sorted(obs.available, key=lambda t: t.tw_end_s)
        for task in available:
            best = self._best_assignment(sim, task.request_id)
            if best is None:
                if task.tw_end_s <= obs.now_s:
                    actions.reject_request(task.request_id)
                continue
            vid, pos, score, detail = best
            ok = actions.claim_task(vid, task.request_id, force_position=pos)
            if ok and detail.get("differs_from_min_travel"):
                self.decision_traces.append(
                    {
                        "time_s": sim.now_s,
                        "request_id": task.request_id,
                        "chosen_vehicle": vid,
                        "chosen_position": pos,
                        "score": score,
                        **detail,
                    }
                )

        if self.allow_reassign:
            self._reassignment_pass(sim)

        self.charging.apply(sim, actions)

    def _restricted_self_pass(self, obs: RestrictedObservation, actions: ActionInterface) -> None:
        sim = actions._sim
        best_task = None
        best_pos = None
        best_score = None
        for task in sorted(obs.announced, key=lambda t: t.tw_end_s):
            cands = self._vehicle_candidates(sim, obs.vehicle_id, task.request_id)
            if not cands:
                if task.tw_end_s <= obs.now_s:
                    actions.reject_request(task.request_id)
                continue
            score, pos, _ = cands[0]
            if best_score is None or score < best_score:
                best_score = score
                best_task = task.request_id
                best_pos = pos
        if best_task is not None:
            actions.claim_task(obs.vehicle_id, best_task, force_position=best_pos)

    def _shadow_prices(self, phi_e: float, phi_t: float) -> tuple[float, float]:
        if self.pricing_mode == "fixed_weight":
            return float(self.fixed_mu_e), float(self.fixed_mu_t)
        mu_e = self.alpha_energy / (self.eps + max(0.0, phi_e) / max(1e-6, self.e_typical_kwh))
        mu_t = self.beta_time * (
            self.t_typical_s / (self.eps * self.t_typical_s + max(0.0, phi_t))
        )
        return mu_e, mu_t

    def _score_candidate(self, chk) -> float:
        dt = float(chk.marginal_travel_s)
        if not self.use_flexibility_pricing:
            return dt
        phi_e0 = float(chk.baseline_energy_flex_kwh)
        phi_t0 = float(chk.baseline_min_deadline_slack_s)
        d_e = max(0.0, phi_e0 - float(chk.energy_flex_kwh))
        d_t = max(0.0, phi_t0 - float(chk.min_deadline_slack_s))
        mu_e, mu_t = self._shadow_prices(phi_e0, phi_t0)
        return dt + mu_e * d_e + mu_t * d_t

    def _vehicle_candidates(self, sim, vehicle_id: str, request_id: str) -> list[tuple[float, int, Any]]:
        req = sim.requests[request_id]
        cands = evaluate_insertion(
            sim.vehicles[vehicle_id],
            req,
            sim.requests,
            sim.router,
            sim.energy,
            sim.depot_node,
            sim.payload_max,
            sim.shift_end_s,
            sim.now_s,
        )
        scored = []
        for chk in cands:
            assert chk.insert_position is not None
            scored.append((self._score_candidate(chk), chk.insert_position, chk))
        scored.sort(key=lambda x: x[0])
        return scored

    def _best_assignment(self, sim, request_id: str):
        best = None
        min_travel = None
        min_travel_choice = None
        for vid in sim.vehicles:
            for score, pos, chk in self._vehicle_candidates(sim, vid, request_id):
                if min_travel is None or chk.marginal_travel_s < min_travel:
                    min_travel = chk.marginal_travel_s
                    min_travel_choice = (vid, pos)
                if best is None or score < best[2]:
                    best = (vid, pos, score, chk)
        if best is None:
            return None
        vid, pos, score, chk = best
        differs = min_travel_choice is not None and (vid, pos) != min_travel_choice
        detail = {
            "marginal_travel_s": chk.marginal_travel_s,
            "marginal_energy_kwh": chk.marginal_energy_kwh,
            "d_energy_flex": max(0.0, chk.baseline_energy_flex_kwh - chk.energy_flex_kwh),
            "d_deadline_slack": max(0.0, chk.baseline_min_deadline_slack_s - chk.min_deadline_slack_s),
            "min_travel_vehicle": None if min_travel_choice is None else min_travel_choice[0],
            "min_travel_position": None if min_travel_choice is None else min_travel_choice[1],
            "differs_from_min_travel": differs,
        }
        return vid, pos, score, detail

    def _current_plan_metrics(self, sim, vehicle_id: str):
        v = sim.vehicles[vehicle_id]
        proj = projected_state_after_lock(
            v, sim.requests, sim.router, sim.energy, sim.depot_node, sim.now_s
        )
        plan = [s for s in editable_suffix(v) if s.kind == "pickup"]
        return simulate_plan_conservative(
            proj,
            plan,
            sim.requests,
            sim.router,
            sim.energy,
            sim.depot_node,
            sim.payload_max,
            sim.shift_end_s,
        )

    def _reassignment_pass(self, sim) -> None:
        movable: list[tuple[str, str]] = []
        for vid, v in sim.vehicles.items():
            locked = v.moving_to.request_id if (v.moving_to and v.moving_to.kind == "pickup") else None
            for rid in list(v.committed):
                if rid == locked:
                    continue
                req = sim.requests.get(rid)
                if req is None or req.status != RequestStatus.COMMITTED or req.owner != vid:
                    continue
                movable.append((vid, rid))

        for from_v, rid in movable:
            base_from = self._current_plan_metrics(sim, from_v)
            if not base_from.feasible:
                continue
            if base_from.energy_flex_kwh >= self.e_typical_kwh:
                continue

            best_to = None
            best_score = None
            best_pos = None
            req = sim.requests[rid]
            snap_st, snap_ow = req.status, req.owner
            req.status = RequestStatus.AVAILABLE
            req.owner = None
            try:
                for to_v in sim.vehicles:
                    if to_v == from_v:
                        continue
                    base_to = self._current_plan_metrics(sim, to_v)
                    if base_to.feasible and base_to.energy_flex_kwh <= base_from.energy_flex_kwh:
                        continue
                    cands = self._vehicle_candidates(sim, to_v, rid)
                    if not cands:
                        continue
                    score, pos, _ = cands[0]
                    if best_score is None or score < best_score:
                        best_score = score
                        best_to = to_v
                        best_pos = pos
            finally:
                req.status, req.owner = snap_st, snap_ow

            if best_to is not None:
                # try_reassign uses check_insertion (min marginal travel); force via assign path
                if sim.try_reassign(from_v, best_to, rid) and best_pos is not None:
                    pass
