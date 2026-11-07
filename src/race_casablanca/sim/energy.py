"""Stochastic energy model: nominal / realized / conservative.

Disturbances are synthetic Stage-2 parameters, not measured Casablanca van data.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

import numpy as np


@dataclass
class EnergyModel:
    consumption_kwh_per_km: float
    uncertainty_delta: float = 0.0
    battery_kwh_max: float = 40.0
    reserve_soc: float = 0.15
    charge_power_kw: float = 22.0
    # adversarial_worst: always realize +delta (bound tightness test)
    # crn: common-random-numbers via leg key hash
    realization_mode: str = "crn"  # crn | adversarial_worst | stochastic
    scenario_seed: int = 0

    @property
    def reserve_kwh(self) -> float:
        return self.reserve_soc * self.battery_kwh_max

    def distance_km(self, length_m: float) -> float:
        return max(0.0, float(length_m)) / 1000.0

    def nominal_kwh(self, length_m: float) -> float:
        return self.consumption_kwh_per_km * self.distance_km(length_m)

    def conservative_kwh(self, length_m: float) -> float:
        return self.nominal_kwh(length_m) * (1.0 + self.uncertainty_delta)

    def _xi_for_leg(self, vehicle_id: str, leg_seq: int, rng: np.random.Generator) -> float:
        if self.uncertainty_delta <= 0:
            return 0.0
        if self.realization_mode == "adversarial_worst":
            return float(self.uncertainty_delta)
        if self.realization_mode == "stochastic":
            return float(rng.uniform(-self.uncertainty_delta, self.uncertainty_delta))
        # CRN: deterministic xi from (scenario_seed, vehicle, leg_seq)
        key = f"{self.scenario_seed}|{vehicle_id}|{leg_seq}".encode()
        digest = hashlib.sha256(key).digest()
        u = int.from_bytes(digest[:8], "little") / float(2**64 - 1)
        return float(-self.uncertainty_delta + 2.0 * self.uncertainty_delta * u)

    def sample_realized_kwh(
        self,
        length_m: float,
        rng: np.random.Generator,
        *,
        vehicle_id: str = "V",
        leg_seq: int = 0,
    ) -> float:
        xi = self._xi_for_leg(vehicle_id, leg_seq, rng)
        return self.nominal_kwh(length_m) * (1.0 + xi)

    def charge_time_s(self, delta_kwh: float) -> float:
        if delta_kwh <= 0 or self.charge_power_kw <= 0:
            return 0.0
        return (delta_kwh / self.charge_power_kw) * 3600.0
