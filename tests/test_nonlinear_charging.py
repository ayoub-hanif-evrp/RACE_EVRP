"""Non-linear depot charging: duration depends on SOC band (CC–CV style)."""

from __future__ import annotations

from race_casablanca.sim.energy import EnergyModel


def test_late_soc_slower_than_early_soc():
    e = EnergyModel(consumption_kwh_per_km=0.2)
    early = e.charge_duration_s(soc_from=0.10, soc_to=0.30)
    late = e.charge_duration_s(soc_from=0.80, soc_to=1.00)
    assert early > 0 and late > 0
    # Same 0.20 SOC span: CV taper must take longer.
    assert late > early * 1.2


def test_same_delta_kwh_not_constant_time():
    e = EnergyModel(consumption_kwh_per_km=0.2, battery_kwh_max=40.0)
    d_low = e.charge_duration_kwh(kwh_from=4.0, kwh_to=12.0)  # 8 kWh low SOC
    d_high = e.charge_duration_kwh(kwh_from=32.0, kwh_to=40.0)  # 8 kWh high SOC
    assert d_high > d_low


def test_no_linear_charge_time_api():
    e = EnergyModel(consumption_kwh_per_km=0.2)
    assert not hasattr(e, "charge_time_s")
    assert hasattr(e, "charge_duration_s")
    assert hasattr(e, "charge_duration_kwh")


def test_from_fleet_loads_curve():
    fleet = {
        "usable_battery_kwh": 40.0,
        "consumption_wh_per_km": 200.0,
        "min_reserve_soc": 0.15,
        "charging_curve": {
            "soc_breakpoints": [0.0, 0.5, 1.0],
            "cumulative_hours": [0.0, 1.0, 3.0],
            "peak_power_kw": 22.0,
        },
    }
    e = EnergyModel.from_fleet(fleet)
    assert e.charge_duration_s(soc_from=0.0, soc_to=0.5) == 3600.0
    assert e.charge_duration_s(soc_from=0.5, soc_to=1.0) == 7200.0
