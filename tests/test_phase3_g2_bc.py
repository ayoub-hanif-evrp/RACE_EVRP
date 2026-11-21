"""Phase 3 / G2: BC competence helper returns OT metrics on conflict."""

from __future__ import annotations

import pytest


@pytest.mark.slow
def test_eval_bc_g2_smoke_returns_metrics():
    from race_casablanca.marl.phase3_eval import eval_bc_g2

    out = eval_bc_g2(
        bc_steps=24,
        bc_epochs=2,
        dagger_rounds=0,
        n_eval_episodes=1,
        master_seed=0,
        max_decisions=60,
        energy_binding=False,
        teacher_mean_ot=0.0,
    )
    assert "mean_ot" in out
    assert "g2_pass" in out
    assert "g2_relative_pass" in out
    assert out["bc"]["n"] >= 1
    assert 0.0 <= float(out["mean_ot"]) <= 1.0
