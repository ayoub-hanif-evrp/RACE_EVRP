"""Stage 4B exact tiny charge–commitment instances."""

from __future__ import annotations

from race_casablanca.exact.charge_commit_enum import (
    enumerate_charge_commit,
    instance_a_early_charge,
    instance_b_serve_before_charge,
    instance_c_partial_better,
    instance_d_charge_enables_later,
    run_all_canned,
)


def test_canned_instances_run():
    rows = run_all_canned()
    assert len(rows) == 4
    names = {r.instance for r in rows}
    assert "A_early_charge" in names
    assert "B_serve_before_charge" in names
    assert "C_partial_better" in names
    assert "D_charge_enables_later" in names


def test_a_early_charge_serves_with_charge():
    r = enumerate_charge_commit(instance_a_early_charge())
    assert r.best_on_time == 1
    assert any(step.get("op") == "charge" for step in r.best_plan)


def test_b_always_full_worse_or_equal():
    r = enumerate_charge_commit(instance_b_serve_before_charge())
    assert r.best_on_time >= r.always_full_on_time
    assert r.best_on_time == 2
    assert r.always_full_on_time < r.best_on_time


def test_c_partial_beats_always_full():
    r = enumerate_charge_commit(instance_c_partial_better())
    assert r.best_on_time == 1
    assert r.always_full_on_time == 0
    assert any(step.get("op") == "charge" and step.get("target_soc") == 0.5 for step in r.best_plan)


def test_d_charge_enables_two():
    r = enumerate_charge_commit(instance_d_charge_enables_later())
    assert r.best_on_time == 2
    assert r.always_full_on_time < r.best_on_time
