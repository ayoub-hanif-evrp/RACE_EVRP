"""Genuine MAPPO-based RACE-MARL (centralized training, decentralized execution)."""

from race_casablanca.marl.env import RaceMultiAgentEnv
from race_casablanca.marl.mappo import MAPPOTrainer

__all__ = ["RaceMultiAgentEnv", "MAPPOTrainer"]
