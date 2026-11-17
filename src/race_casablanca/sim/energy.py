"""Energy model with non-linear (piecewise-linear SOC–time) depot charging.

Charging follows a concave CC–CV style curve: early SOC rises faster, then
tapers near full. Duration depends on start and end SOC, not ΔkWh / constant kW.

Disturbances for consumption are synthetic Stage-2 parameters, not measured
Casablanca van telemetry.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

import numpy as np

# Default cumulative hours to reach each SOC from empty (40 kWh class van,
# ~22 kW peak depot charger). Near-constant power through mid SOC, then CV taper.
DEFAULT_SOC_BREAKPOINTS = (0.0, 0.50, 0.80, 0.90, 0.95, 1.0)
DEFAULT_CUMULATIVE_HOURS = (0.0, 0.91, 1.46, 1.72, 1.95, 2.40)


def _interp_hours(soc: float, soc_bp: np.ndarray, hours_bp: np.ndarray) -> float:
    s = float(np.clip(soc, 0.0, 1.0))
    return float(np.interp(s, soc_bp, hours_bp))


@dataclass
class EnergyModel:
    consumption_kwh_per_km: float
    uncertainty_delta: float = 0.0
    battery_kwh_max: float = 40.0
    reserve_soc: float = 0.15
    # Non-linear charging curve (cumulative time from SOC 0).
    charge_soc_breakpoints: tuple[float, ...] = DEFAULT_SOC_BREAKPOINTS
    charge_cumulative_hours: tuple[float, ...] = DEFAULT_CUMULATIVE_HOURS
    # Peak charger rating kept for documentation / reporting only (not a linear clock).
    peak_charge_power_kw: float = 22.0
    realization_mode: str = "crn"  # crn | adversarial_worst | stochastic
    scenario_seed: int = 0
    _soc_bp: np.ndarray = field(init=False, repr=False)
    _hours_bp: np.ndarray = field(init=False, repr=False)

    def __post_init__(self) -> None:
        soc = np.asarray(self.charge_soc_breakpoints, dtype=float)
        hrs = np.asarray(self.charge_cumulative_hours, dtype=float)
        if soc.ndim != 1 or hrs.ndim != 1 or len(soc) != len(hrs) or len(soc) < 2:
            raise ValueError("charge curve breakpoints must be 1-D arrays of equal length >= 2")
        if soc[0] != 0.0 or abs(soc[-1] - 1.0) > 1e-9:
            raise ValueError("charge SOC breakpoints must start at 0 and end at 1")
        if np.any(np.diff(soc) <= 0) or np.any(np.diff(hrs) < 0):
            raise ValueError("charge breakpoints must be strictly increasing SOC and nondecreasing hours")
        # Scale curve if peak power differs from the reference curve (~22 kW).
        ref_kw = 22.0
        peak = float(self.peak_charge_power_kw) if self.peak_charge_power_kw > 0 else ref_kw
        scale = ref_kw / peak
        self._soc_bp = soc
        self._hours_bp = hrs * scale

    @classmethod
    def from_fleet(
        cls,
        fleet: dict,
        *,
        uncertainty_delta: float = 0.0,
        realization_mode: str = "crn",
        scenario_seed: int = 0,
    ) -> "EnergyModel":
        cons_wh = float(fleet.get("consumption_wh_per_km", 200.0))
        bat = float(fleet.get("usable_battery_kwh", 40.0))
        curve = fleet.get("charging_curve") or {}
        soc_bp = tuple(curve.get("soc_breakpoints") or DEFAULT_SOC_BREAKPOINTS)
        hrs_bp = tuple(curve.get("cumulative_hours") or DEFAULT_CUMULATIVE_HOURS)
        peak = float(
            curve.get("peak_power_kw")
            or fleet.get("peak_charge_power_kw")
            or 22.0
        )
        return cls(
            consumption_kwh_per_km=cons_wh / 1000.0,
            uncertainty_delta=float(uncertainty_delta),
            battery_kwh_max=bat,
            reserve_soc=float(fleet.get("min_reserve_soc", 0.15)),
            charge_soc_breakpoints=soc_bp,
            charge_cumulative_hours=hrs_bp,
            peak_charge_power_kw=peak,
            realization_mode=str(realization_mode),
            scenario_seed=int(scenario_seed),
        )

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

    def cumulative_charge_hours(self, soc: float) -> float:
        """Hours to charge from empty to ``soc`` along the non-linear curve."""
        return _interp_hours(soc, self._soc_bp, self._hours_bp)

    def charge_duration_s(self, *, soc_from: float, soc_to: float) -> float:
        """Non-linear charge duration between two SOC levels (seconds)."""
        a = float(np.clip(soc_from, 0.0, 1.0))
        b = float(np.clip(soc_to, 0.0, 1.0))
        if b <= a + 1e-15:
            return 0.0
        return max(0.0, (self.cumulative_charge_hours(b) - self.cumulative_charge_hours(a)) * 3600.0)

    def charge_duration_kwh(self, *, kwh_from: float, kwh_to: float) -> float:
        bmax = float(self.battery_kwh_max)
        if bmax <= 0:
            return 0.0
        return self.charge_duration_s(soc_from=kwh_from / bmax, soc_to=kwh_to / bmax)

    def marginal_hours_per_soc(self, soc: float) -> float:
        """Local slope dh/dsoc (hours per SOC unit); increases in the CV taper."""
        s = float(np.clip(soc, 0.0, 1.0))
        # Finite difference on the piecewise-linear curve.
        for i in range(len(self._soc_bp) - 1):
            if self._soc_bp[i] <= s <= self._soc_bp[i + 1] + 1e-15:
                ds = self._soc_bp[i + 1] - self._soc_bp[i]
                if ds <= 0:
                    return 0.0
                return float((self._hours_bp[i + 1] - self._hours_bp[i]) / ds)
        return float((self._hours_bp[-1] - self._hours_bp[-2]) / (self._soc_bp[-1] - self._soc_bp[-2]))
