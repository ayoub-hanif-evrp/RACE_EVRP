"""Stochastic energy model: nominal / realized / conservative.

Disturbances are synthetic Stage-2 parameters, not measured Casablanca van data.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class EnergyModel:
    consumption_kwh_per_km: float
    uncertainty_delta: float = 0.0
    battery_kwh_max: float = 40.0
    reserve_soc: float = 0.15
    charge_power_kw: float = 22.0

    @property
    def reserve_kwh(self) -> float:
        return self.reserve_soc * self.battery_kwh_max

    def distance_km(self, length_m: float) -> float:
        return max(0.0, float(length_m)) / 1000.0

    def nominal_kwh(self, length_m: float) -> float:
        return self.consumption_kwh_per_km * self.distance_km(length_m)

    def conservative_kwh(self, length_m: float) -> float:
        return self.nominal_kwh(length_m) * (1.0 + self.uncertainty_delta)

    def sample_realized_kwh(self, length_m: float, rng: np.random.Generator) -> float:
        if self.uncertainty_delta <= 0:
            return self.nominal_kwh(length_m)
        xi = float(rng.uniform(-self.uncertainty_delta, self.uncertainty_delta))
        return self.nominal_kwh(length_m) * (1.0 + xi)

    def charge_time_s(self, delta_kwh: float) -> float:
        if delta_kwh <= 0 or self.charge_power_kw <= 0:
            return 0.0
        return (delta_kwh / self.charge_power_kw) * 3600.0
