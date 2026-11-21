"""G5 structural: NL taper + exact partial-better instance."""

from __future__ import annotations

from race_casablanca.marl.g5_nl_charge import exact_partial_beats_full, nl_taper_costs


def test_nl_taper_full_slower_than_partial():
    t = nl_taper_costs(soc_from=0.28)
    assert t["full_to_1_00_s"] > t["partial_to_0_70_s"] * 1.5
    assert t["taper_0_70_to_1_00_s"] > 0


def test_exact_partial_beats_always_full():
    r = exact_partial_beats_full()
    assert r["pass"]
    assert r["best_on_time"] > r["always_full_on_time"]
