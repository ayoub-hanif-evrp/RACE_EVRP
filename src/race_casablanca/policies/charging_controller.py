"""Shared depot-charging decision rule for fair baseline comparisons.

Modes
-----
none:
    Never request charge from the controller.
always_on_return:
    Idle empty vehicles return with charge=True to full (target_soc=1.0).
adaptive_headroom:
    Idle empty vehicles charge when battery headroom below threshold;
    default target is full (1.0). Gap experiments may set target_soc=0.7.
charge_to_target:
    Like always_on_return but uses ``target_soc`` (discrete alphabet).

Discrete target alphabet (Stage 4B): {noop, 0.50, 0.70, 1.00} clipped to
[current_soc, 1]. Controllers never invent public chargers or price markets.
"""

from __future__ import annotations

from dataclasses import dataclass

from race_casablanca.sim.policy_api import ActionInterface

# Canonical discrete target-SOC set for Stage 4B equalized experiments
DISCRETE_TARGET_SOCS: tuple[float, ...] = (0.50, 0.70, 1.00)


@dataclass
class ChargingController:
    mode: str = "adaptive_headroom"  # none | always_on_return | adaptive_headroom | charge_to_target
    headroom_threshold_kwh: float = 3.0
    target_soc: float = 1.0  # used by always_on / adaptive / charge_to_target

    def apply(self, sim, actions: ActionInterface) -> int:
        """Issue charge/return actions for eligible idle vehicles. Returns n charged."""

        if self.mode == "none":
            return 0
        n = 0
        tgt = float(self.target_soc)
        for vid, v in sim.vehicles.items():
            if v.busy or str(getattr(v.mode, "value", v.mode)) == "emergency_stranded":
                continue
            if any(s.kind == "pickup" for s in v.plan):
                continue
            if any(s.kind.startswith("depot") for s in v.plan):
                continue
            headroom = float(v.battery_kwh) - float(sim.energy.reserve_kwh)
            bmax = float(sim.energy.battery_kwh_max)
            current_soc = float(v.battery_kwh) / bmax if bmax > 0 else 1.0
            # Already at or above requested target — skip
            if current_soc >= tgt - 1e-6:
                continue
            at_depot = int(v.node) == int(sim.depot_node)
            if self.mode == "always_on_return":
                want = True
                use_tgt = 1.0
            elif self.mode == "charge_to_target":
                want = True
                use_tgt = tgt
            elif self.mode == "adaptive_headroom":
                want = headroom < self.headroom_threshold_kwh
                use_tgt = tgt  # default full; experiments may set 0.7
            else:
                want = False
                use_tgt = tgt
            if not want:
                continue
            if at_depot and current_soc >= use_tgt - 1e-6:
                continue
            # Explicit per-call charge; do not mutate sim.config.charge_on_return
            actions.request_return_depot(vid, charge=True, target_soc=use_tgt)
            n += 1
        return n
