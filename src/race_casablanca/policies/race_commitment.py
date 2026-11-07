"""RACE — Risk-Aware Commitment and Energy management (non-learning prototype).

Hard constraints: same conservative energy / time-window / payload / depot-return
feasibility gate as the baselines.

Soft ranking among feasible insertions: state-dependent residual flexibility
opportunity cost (energy and deadline slack), not a fixed weighted penalty.
"""

from __future__ import annotations

from dataclasses import dataclass

from race_casablanca.sim.feasibility_check import (
    editable_suffix,
    projected_state_after_lock,
    simulate_plan_conservative,
)
from race_casablanca.sim.policy_api import ActionInterface, FullInfoObservation, RestrictedObservation
from race_casablanca.sim.types import RequestStatus


@dataclass
class RaceCommitmentPolicy:
    """Full-information risk-aware commitment policy.

    Parameters
    ----------
    use_opportunity_cost:
        If False, ranking reduces to min conservative travel among feasible
        insertions (robust greedy ablation).
    alpha_energy:
        Base seconds-equivalent scale for energy-flexibility scarcity.
    beta_time:
        Relative weight on temporal-slack loss.
    e_typical_kwh / t_typical_s:
        Normalization scales for residual flexibility (not demand forecasts).
    charge_flex_threshold_kwh:
        Idle vehicles below this energy headroom may return to charge.
    allow_reassign:
        One bounded flexibility-driven reassignment pass after primary claims.
    """

    name: str = "race_commitment"
    use_opportunity_cost: bool = True
    alpha_energy: float = 240.0
    beta_time: float = 0.5
    e_typical_kwh: float = 2.0
    t_typical_s: float = 900.0
    charge_flex_threshold_kwh: float = 3.0
    allow_reassign: bool = True
    eps: float = 0.25

    def on_decision(
        self,
        obs: FullInfoObservation | RestrictedObservation,
        actions: ActionInterface,
        reason: str,
    ) -> None:
        if isinstance(obs, RestrictedObservation):
            self._restricted_self_pass(obs, actions)
            return
        if not isinstance(obs, FullInfoObservation):
            return
        if reason == "message":
            return

        sim = actions._sim
        available = sorted(obs.available, key=lambda t: t.tw_end_s)
        for task in available:
            best_v = None
            best_score = None
            for vid in obs.vehicles:
                score = self._insertion_score(sim, vid, task.request_id)
                if score is None:
                    continue
                if best_score is None or score < best_score:
                    best_score = score
                    best_v = vid
            if best_v is None:
                if task.tw_end_s <= obs.now_s:
                    actions.reject_request(task.request_id)
                continue
            actions.claim_task(best_v, task.request_id)

        if self.allow_reassign and self.use_opportunity_cost:
            self._reassignment_pass(sim)

        self._maybe_charge(sim, actions)

    def _restricted_self_pass(self, obs: RestrictedObservation, actions: ActionInterface) -> None:
        """Restricted-info variant: decide only for self (no peer truth)."""

        sim = actions._sim
        best_task = None
        best_score = None
        for task in sorted(obs.announced, key=lambda t: t.tw_end_s):
            score = self._insertion_score(sim, obs.vehicle_id, task.request_id)
            if score is None:
                if task.tw_end_s <= obs.now_s:
                    actions.reject_request(task.request_id)
                continue
            if best_score is None or score < best_score:
                best_score = score
                best_task = task.request_id
        if best_task is not None:
            actions.claim_task(obs.vehicle_id, best_task)

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

    def _shadow_prices(self, phi_e: float, phi_t: float) -> tuple[float, float]:
        mu_e = self.alpha_energy / (self.eps + max(0.0, phi_e) / max(1e-6, self.e_typical_kwh))
        mu_t = self.beta_time * (
            self.t_typical_s / (self.eps * self.t_typical_s + max(0.0, phi_t))
        )
        return mu_e, mu_t

    def _insertion_score(self, sim, vehicle_id: str, request_id: str) -> float | None:
        base = self._current_plan_metrics(sim, vehicle_id)
        has_edit = any(s.kind == "pickup" for s in editable_suffix(sim.vehicles[vehicle_id]))
        if not base.feasible and has_edit:
            return None
        chk = sim.check_insertion(vehicle_id, request_id)
        if not chk.feasible:
            return None
        travel = float(chk.added_travel_s)
        if not self.use_opportunity_cost:
            return travel
        phi_e0 = float(base.energy_flex_kwh) if base.feasible else 0.0
        phi_t0 = float(base.min_deadline_slack_s) if base.feasible else 0.0
        phi_e1 = float(chk.energy_flex_kwh)
        phi_t1 = float(chk.min_deadline_slack_s)
        mu_e, mu_t = self._shadow_prices(phi_e0, phi_t0)
        return travel + mu_e * max(0.0, phi_e0 - phi_e1) + mu_t * max(0.0, phi_t0 - phi_t1)

    def _reassignment_pass(self, sim) -> None:
        """Move a non-locked commitment from a scarce vehicle to a more flexible one."""

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
                continue  # not scarce enough to justify churn

            best_to = None
            best_score = None
            req = sim.requests[rid]
            snap_st, snap_ow = req.status, req.owner
            req.status = RequestStatus.AVAILABLE
            req.owner = None
            try:
                for to_v in sim.vehicles:
                    if to_v == from_v:
                        continue
                    base_to = self._current_plan_metrics(sim, to_v)
                    if not base_to.feasible and any(
                        s.kind == "pickup" for s in editable_suffix(sim.vehicles[to_v])
                    ):
                        continue
                    if base_to.feasible and base_to.energy_flex_kwh <= base_from.energy_flex_kwh:
                        continue
                    score = self._insertion_score(sim, to_v, rid)
                    if score is None:
                        continue
                    if best_score is None or score < best_score:
                        best_score = score
                        best_to = to_v
            finally:
                req.status, req.owner = snap_st, snap_ow

            if best_to is not None:
                sim.try_reassign(from_v, best_to, rid)

    def _maybe_charge(self, sim, actions: ActionInterface) -> None:
        for vid, v in sim.vehicles.items():
            if v.busy or str(v.mode.value) == "emergency_stranded":
                continue
            if any(s.kind == "pickup" for s in v.plan):
                continue
            headroom = v.battery_kwh - sim.energy.reserve_kwh
            if headroom < self.charge_flex_threshold_kwh:
                sim.config.charge_on_return = True
                actions.request_return_depot(vid, charge=True)
