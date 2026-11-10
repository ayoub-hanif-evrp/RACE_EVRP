"""Genuine MAPPO-based RACE-MARL (centralized training, decentralized execution)."""

from race_casablanca.marl.env import (
    ABLATION_A,
    ABLATION_B,
    ABLATION_C,
    ABLATION_D,
    ABLATION_E,
    ABLATION_F,
    RaceMultiAgentEnv,
)
from race_casablanca.marl.mappo import MAPPOTrainer

__all__ = [
    "RaceMultiAgentEnv",
    "MAPPOTrainer",
    "ABLATION_A",
    "ABLATION_B",
    "ABLATION_C",
    "ABLATION_D",
    "ABLATION_E",
    "ABLATION_F",
]
