"""Episode metrics for online baselines."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class EpisodeMetrics:
    scenario_id: str
    policy: str
    info_mode: str
    seed: int
    n_requests: int = 0
    n_served: int = 0
    n_on_time: int = 0
    n_rejected: int = 0
    n_expired: int = 0
    serve_rate: float = 0.0
    on_time_rate_served: float = 0.0
    on_time_rate_all: float = 0.0
    # backward-compatible alias filled in finalize
    on_time_rate: float = 0.0
    total_distance_m: float = 0.0
    total_travel_s: float = 0.0
    total_wait_s: float = 0.0
    energy_consumed_kwh: float = 0.0
    battery_reserve_violations: int = 0
    battery_exhaustion: int = 0
    planned_energy_rejections: int = 0
    payload_violations: int = 0
    n_depot_returns: int = 0
    n_charges: int = 0
    n_messages: int = 0
    n_claims: int = 0
    n_failed_claims: int = 0
    n_reassignments: int = 0
    mean_message_delay_s: float = 0.0
    mean_info_age_s: float = 0.0
    mean_decision_runtime_s: float = 0.0
    n_decisions: int = 0
    energy_changed_dispatch: int = 0
    notes: list[str] = field(default_factory=list)
    config: dict = field(default_factory=dict)

    def finalize(self) -> None:
        self.serve_rate = self.n_served / self.n_requests if self.n_requests else 0.0
        self.on_time_rate_served = self.n_on_time / self.n_served if self.n_served else 0.0
        self.on_time_rate_all = self.n_on_time / self.n_requests if self.n_requests else 0.0
        self.on_time_rate = self.on_time_rate_served

    def to_dict(self) -> dict:
        self.finalize()
        return asdict(self)
