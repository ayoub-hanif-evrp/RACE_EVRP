"""RACE post-decision service-capacity policy (Stage 4A, non-learning).

Estimates future on-time service after each safe candidate action using shared
synthetic continuations and a transparent greedy base rollout. Charging is an
endogenous candidate, not a separate threshold controller.

This is a pilot anticipatory method — not claimed novel versus classical rollout
by itself; novelty requires empirical/theoretical distinction (see Stage 4A reports).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from race_casablanca.demand.synthetic_futures import SyntheticFutureModel
from race_casablanca.sim.feasibility_check import evaluate_insertion
from race_casablanca.sim.lookahead import CandidateAction, score_action
from race_casablanca.sim.policy_api import ActionInterface, FullInfoObservation, RestrictedObservation


@dataclass
class RacePostDecisionPolicy:
    name: str = "race_postdecision"
    n_samples: int = 3
    n_synthetic_requests: int = 4
    max_claim_candidates: int = 8
    max_charge_candidates: int = 3
    enable_future_eval: bool = True
    enable_charge_actions: bool = True
    base_charge_mode: str = "adaptive_headroom"
    lookahead_horizon_s: float | None = 3600.0
    future_model: SyntheticFutureModel | None = None
    seed: int = 0
    decision_log: list[dict[str, Any]] = field(default_factory=list)
    total_lookahead_runtime_s: float = 0.0
    _model_loaded: bool = False

    def _ensure_model(self) -> SyntheticFutureModel:
        if self.future_model is None:
            self.future_model = SyntheticFutureModel.from_training()
            self._model_loaded = True
        return self.future_model

    def on_decision(
        self,
        obs: FullInfoObservation | RestrictedObservation,
        actions: ActionInterface,
        reason: str,
    ) -> None:
        if not isinstance(obs, FullInfoObservation):
            return
        if reason == "message":
            return
        sim = actions._sim

        if not self.enable_future_eval:
            # Ablation: marginal greedy claims + optional charge candidates without MC
            self._myopic_fallback(obs, actions)
            return

        model = self._ensure_model()
        rng = np.random.default_rng(self.seed + int(sim.now_s) // 60)
        # Identical continuations for all candidates (CRN across actions)
        continuations = [
            model.sample_continuation(
                rng,
                now_s=sim.now_s,
                shift_end_s=sim.shift_end_s,
                n_requests=self.n_synthetic_requests,
                prefix=f"k{k}",
            )
            for k in range(self.n_samples)
        ]

        # One anticipatory step (claim / charge / noop), then myopic fill for remaining
        candidates = self._generate_candidates(sim, obs)
        if not candidates:
            return

        scored = [
            score_action(
                sim,
                a,
                continuations,
                base_charge_mode=self.base_charge_mode,
                horizon_s=self.lookahead_horizon_s,
            )
            for a in candidates
        ]
        self.total_lookahead_runtime_s += sum(s.runtime_s for s in scored)

        def key(s):
            return (s.mean_on_time, s.mean_served, -s.mean_travel_s, -s.mean_energy_kwh)

        best = max(scored, key=key)
        self.decision_log.append(
            {
                "time_s": sim.now_s,
                "reason": reason,
                "n_candidates": len(candidates),
                "chosen": best.action.label or best.action.kind,
                "mean_on_time": best.mean_on_time,
                "mean_served": best.mean_served,
                "lookahead_s": sum(s.runtime_s for s in scored),
            }
        )
        self._commit(actions, best.action)
        if best.action.kind != "charge":
            # Fill remaining available with marginal greedy (same hard gate; no nested MC)
            self._myopic_claims_only(sim, actions)
        # Shared reactive charging after anticipatory step (endogenous charge may already have fired)
        if self.enable_charge_actions:
            from race_casablanca.policies.charging_controller import ChargingController

            ChargingController(mode=self.base_charge_mode).apply(sim, actions)

    def _myopic_claims_only(self, sim, actions: ActionInterface) -> None:
        from race_casablanca.sim.policy_api import build_full_observation

        obs = build_full_observation(sim)
        for task in sorted(obs.available, key=lambda t: t.tw_end_s):
            best_v, best_pos, best_c = None, None, None
            for vid in obs.vehicles:
                chk = actions.check_insertion(vid, task.request_id)
                if not chk.feasible:
                    continue
                if best_c is None or chk.marginal_travel_s < best_c:
                    best_c = chk.marginal_travel_s
                    best_v = vid
                    best_pos = chk.insert_position
            if best_v is not None:
                actions.claim_task(best_v, task.request_id, force_position=best_pos)

    def _myopic_fallback(self, obs: FullInfoObservation, actions: ActionInterface) -> None:
        sim = actions._sim
        self._myopic_claims_only(sim, actions)
        if self.enable_charge_actions:
            for vid, v in sim.vehicles.items():
                if v.busy:
                    continue
                head = v.battery_kwh - sim.energy.reserve_kwh
                if head < 3.0 and v.battery_kwh < sim.energy.battery_kwh_max - 1e-6:
                    actions.request_return_depot(vid, charge=True)
                    break

    def _generate_candidates(self, sim, obs: FullInfoObservation) -> list[CandidateAction]:
        cands: list[CandidateAction] = [CandidateAction(kind="noop", label="noop")]
        # Claim candidates: earliest deadlines first
        tasks = sorted(obs.available, key=lambda t: t.tw_end_s)[:4]
        claim_budget = self.max_claim_candidates
        for task in tasks:
            scored_ins = []
            for vid in obs.vehicles:
                req = sim.requests[task.request_id]
                inserts = evaluate_insertion(
                    sim.vehicles[vid],
                    req,
                    sim.requests,
                    sim.router,
                    sim.energy,
                    sim.depot_node,
                    sim.payload_max,
                    sim.shift_end_s,
                    sim.now_s,
                )
                for chk in inserts:
                    scored_ins.append((chk.marginal_travel_s, vid, chk.insert_position))
            scored_ins.sort(key=lambda x: x[0])
            for marg, vid, pos in scored_ins[:2]:
                if claim_budget <= 0:
                    break
                cands.append(
                    CandidateAction(
                        kind="claim",
                        vehicle_id=vid,
                        request_id=task.request_id,
                        position=pos,
                        label=f"claim:{task.request_id}@{vid}:{pos}",
                    )
                )
                claim_budget -= 1
            if claim_budget <= 0:
                break

        if self.enable_charge_actions:
            n_ch = 0
            for vid, v in sim.vehicles.items():
                if n_ch >= self.max_charge_candidates:
                    break
                if v.busy:
                    continue
                if any(s.kind == "pickup" for s in v.plan):
                    continue
                if float(v.battery_kwh) >= float(sim.energy.battery_kwh_max) - 1e-6:
                    continue
                # Eligible when not full — endogenous evaluation decides whether worth it
                cands.append(
                    CandidateAction(kind="charge", vehicle_id=vid, label=f"charge:{vid}")
                )
                n_ch += 1
        return cands

    def _commit(self, actions: ActionInterface, action: CandidateAction) -> None:
        if action.kind == "noop":
            return
        if action.kind == "claim":
            actions.claim_task(action.vehicle_id, action.request_id, force_position=action.position)
            return
        if action.kind == "charge":
            actions.request_return_depot(action.vehicle_id, charge=True)
