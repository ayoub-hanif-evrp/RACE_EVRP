"""Shared depot-charging decision rule for fair baseline comparisons.

Modes
-----
none:
    Never request charge from the controller.
always_on_return:
    Idle empty vehicles return with charge=True.
adaptive_headroom:
    Idle empty vehicles charge when battery headroom below threshold.
"""

from __future__ import annotations

from dataclasses import dataclass

from race_casablanca.sim.policy_api import ActionInterface


@dataclass
class ChargingController:
    mode: str = "adaptive_headroom"  # none | always_on_return | adaptive_headroom
    headroom_threshold_kwh: float = 3.0

    def apply(self, sim, actions: ActionInterface) -> int:
        """Issue charge/return actions for eligible idle vehicles. Returns n charged."""

        if self.mode == "none":
            return 0
        n = 0
        for vid, v in sim.vehicles.items():
            if v.busy or str(getattr(v.mode, "value", v.mode)) == "emergency_stranded":
                continue
            if any(s.kind == "pickup" for s in v.plan):
                continue
            if any(s.kind.startswith("depot") for s in v.plan):
                continue
            headroom = float(v.battery_kwh) - float(sim.energy.reserve_kwh)
            # Already full (or nearly) at depot — do not re-queue charge forever
            nearly_full = float(v.battery_kwh) >= float(sim.energy.battery_kwh_max) - 1e-6
            at_depot = int(v.node) == int(sim.depot_node)
            if nearly_full:
                continue
            if self.mode == "always_on_return":
                want = True
            elif self.mode == "adaptive_headroom":
                want = headroom < self.headroom_threshold_kwh
            else:
                want = False
            if not want:
                continue
            if at_depot and nearly_full:
                continue
            # Explicit per-call charge; do not mutate sim.config.charge_on_return
            actions.request_return_depot(vid, charge=True)
            n += 1
        return n
