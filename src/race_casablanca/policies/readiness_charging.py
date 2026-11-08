"""Proactive depot readiness charging (Stage 5.1).

Uses only observable state — no hidden future requests.
Discrete target from alphabet {0.50, 0.70, 1.00}. Shared by RACE-RH and
conventional charge-aware RH so fairness is preserved.
"""

from __future__ import annotations

from dataclasses import dataclass

from race_casablanca.sim.policy_api import ActionInterface
from race_casablanca.sim.types import VehicleMode


@dataclass
class ReadinessChargingController:
    """Charge idle empty vehicles up to a readiness SOC when headroom is low."""

    target_soc: float = 0.70
    # Trigger when current SOC is below target by at least this absolute gap
    min_soc_gap: float = 0.05
    enabled: bool = True
    n_proactive_charges: int = 0

    def apply(self, sim, actions: ActionInterface) -> int:
        if not self.enabled:
            return 0
        n = 0
        bmax = float(sim.energy.battery_kwh_max)
        tgt = float(self.target_soc)
        for vid, v in sim.vehicles.items():
            if v.busy or v.mode == VehicleMode.EMERGENCY_STRANDED:
                continue
            if any(s.kind == "pickup" for s in v.plan):
                continue
            if any(s.kind.startswith("depot") for s in v.plan):
                continue
            # Urgent released work that this vehicle can claim without charging first
            # → skip readiness so we do not burn deadline window
            if self._has_urgent_claimable_work(sim, actions, vid):
                continue
            soc = float(v.battery_kwh) / bmax if bmax > 0 else 1.0
            if soc >= tgt - self.min_soc_gap:
                continue
            actions.request_return_depot(vid, charge=True, target_soc=tgt)
            self.n_proactive_charges += 1
            n += 1
        return n

    def _has_urgent_claimable_work(self, sim, actions: ActionInterface, vid: str) -> bool:
        """True if an available request is feasibly insertable now without a charge stop."""
        from race_casablanca.sim.types import RequestStatus

        for req in sim.requests.values():
            if req.status != RequestStatus.AVAILABLE:
                continue
            # Urgency: window closes within 30 min of now
            if req.tw_end_s > sim.now_s + 1800.0:
                continue
            try:
                chk = actions.check_insertion(vid, req.request_id)
            except Exception:  # noqa: BLE001
                continue
            if chk.feasible:
                return True
        return False
