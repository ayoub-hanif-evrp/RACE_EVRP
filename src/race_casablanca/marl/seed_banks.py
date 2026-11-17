"""Reserved scenario seeds for Casablanca MARL / evaluation hygiene.

Training must never reuse locked_final, evaluation_v1/default, or release
split seeds. Procedural MARL episodes live in TRAIN_SEED_RANGE only.
"""

from __future__ import annotations

from typing import Iterable

# Release casablanca_release_v1 (small diagnostic files on disk).
RELEASE_TRAIN_SEEDS = frozenset(range(1, 9))
RELEASE_VAL_SEEDS = frozenset({101, 102})
RELEASE_TEST_SEEDS = frozenset({201, 202, 203})

# evaluation_v1/default materialized / registered banks.
EVAL_DEFAULT_SEEDS = frozenset(
    list(range(1101, 1121)) + list(range(1201, 1221)) + list(range(1301, 1321))
)

# locked_final materialized (10/regime) + registered fuller bank (30/regime).
LOCKED_FINAL_SEEDS = frozenset(
    list(range(2101, 2131)) + list(range(2201, 2231)) + list(range(2301, 2331))
)

FORBIDDEN_TRAIN_SEEDS = (
    RELEASE_TRAIN_SEEDS
    | RELEASE_VAL_SEEDS
    | RELEASE_TEST_SEEDS
    | EVAL_DEFAULT_SEEDS
    | LOCKED_FINAL_SEEDS
)

# Inclusive procedural train range for on-the-fly generator episodes.
TRAIN_SEED_RANGE = (10_000_000, 19_999_999)

REGIME_ORDER = ("baseline", "peak_stress", "tight_windows")


def is_forbidden_train_seed(seed: int) -> bool:
    return int(seed) in FORBIDDEN_TRAIN_SEEDS


def assert_train_seed_allowed(seed: int) -> int:
    s = int(seed)
    lo, hi = TRAIN_SEED_RANGE
    if not (lo <= s <= hi):
        raise ValueError(
            f"Train seed {s} outside procedural range [{lo}, {hi}]; "
            "refusing possible contamination of reserved evaluation banks."
        )
    if is_forbidden_train_seed(s):
        raise ValueError(f"Train seed {s} collides with a reserved evaluation bank")
    return s


def episode_train_seed(master_seed: int, episode_index: int) -> int:
    """Deterministic unique seed in TRAIN_SEED_RANGE for (master, episode)."""
    lo, hi = TRAIN_SEED_RANGE
    span = hi - lo + 1
    # Mix master and episode; stay inside range.
    mixed = (int(master_seed) * 1_000_003 + int(episode_index) * 97_421 + 17) % span
    return assert_train_seed_allowed(lo + mixed)


def curriculum_regime(episode_index: int, order: Iterable[str] = REGIME_ORDER) -> str:
    regimes = tuple(order)
    return regimes[int(episode_index) % len(regimes)]
