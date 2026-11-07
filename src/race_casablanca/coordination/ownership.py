"""Minimal transactional task-ownership registry.

This is a central authority used to prevent duplicate pickup claims.
Restricted-information policies that depend on it are therefore not fully
decentralized; the registry's availability and message costs are documented.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ClaimRecord:
    request_id: str
    owner: str
    claimed_at_s: float


@dataclass
class TaskRegistry:
    claims: dict[str, ClaimRecord] = field(default_factory=dict)
    n_rejected_duplicates: int = 0

    def owner_of(self, request_id: str) -> str | None:
        rec = self.claims.get(request_id)
        return rec.owner if rec else None

    def try_claim(self, request_id: str, vehicle_id: str, time_s: float) -> bool:
        if request_id in self.claims:
            if self.claims[request_id].owner != vehicle_id:
                self.n_rejected_duplicates += 1
                return False
            return True
        self.claims[request_id] = ClaimRecord(request_id, vehicle_id, time_s)
        return True

    def release(self, request_id: str, vehicle_id: str) -> bool:
        rec = self.claims.get(request_id)
        if rec is None:
            return False
        if rec.owner != vehicle_id:
            return False
        del self.claims[request_id]
        return True

    def transfer(self, request_id: str, from_v: str, to_v: str, time_s: float) -> bool:
        if not self.release(request_id, from_v):
            return False
        return self.try_claim(request_id, to_v, time_s)
