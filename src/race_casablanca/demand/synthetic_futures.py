"""Training-side synthetic future request model (Stage 4A).

Built only from frozen training scenario request tables. Never reads validation/test
or the evaluation scenario's unreleased requests.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from race_casablanca.paths import scenarios_dir
from race_casablanca.sim.types import Request, RequestStatus


@dataclass
class SyntheticFutureModel:
    """Low-dimensional empirical sampler over training request attributes."""

    release_offsets_s: np.ndarray
    snap_nodes: np.ndarray
    tw_durations_s: np.ndarray
    service_s: np.ndarray
    weights_kg: np.ndarray
    source_scenarios: tuple[str, ...]

    @classmethod
    def from_training(cls, train_ids: list[str] | None = None) -> "SyntheticFutureModel":
        train_ids = train_ids or [
            "baseline_seed1",
            "baseline_seed4",
            "peak_stress_seed2",
            "peak_stress_seed5",
            "tight_windows_seed3",
            "tight_windows_seed6",
        ]
        rows = []
        for sid in train_ids:
            path = scenarios_dir() / "train" / sid / "requests.csv"
            if not path.exists():
                continue
            df = pd.read_csv(path)
            # Casablanca CSVs use minutes; convert to seconds
            if "release_s" in df.columns:
                rel_col, tw0, tw1, svc_col = "release_s", "tw_start_s", "tw_end_s", "service_s"
                scale = 1.0
            else:
                rel_col, tw0, tw1, svc_col = "release_min", "tw_start_min", "tw_end_min", "service_min"
                scale = 60.0
            t0 = float(df[rel_col].min()) * scale
            for _, r in df.iterrows():
                rel = float(r[rel_col]) * scale - t0
                tw = (float(r[tw1]) - float(r[tw0])) * scale
                svc = float(r[svc_col]) * scale if svc_col in df.columns else 60.0
                rows.append(
                    {
                        "rel": max(0.0, rel),
                        "node": int(r["snap_node"]),
                        "tw": max(300.0, tw),
                        "svc": max(1.0, svc),
                        "w": float(r.get("weight_kg", 10.0)),
                    }
                )
        if not rows:
            # Tiny fallback for unit tests without CSV
            return cls(
                release_offsets_s=np.array([0.0, 600.0, 1800.0]),
                snap_nodes=np.array([1, 2, 3]),
                tw_durations_s=np.array([1800.0, 3600.0]),
                service_s=np.array([60.0]),
                weights_kg=np.array([10.0]),
                source_scenarios=tuple(train_ids),
            )
        return cls(
            release_offsets_s=np.array([r["rel"] for r in rows], dtype=float),
            snap_nodes=np.array([r["node"] for r in rows], dtype=int),
            tw_durations_s=np.array([r["tw"] for r in rows], dtype=float),
            service_s=np.array([r["svc"] for r in rows], dtype=float),
            weights_kg=np.array([r["w"] for r in rows], dtype=float),
            source_scenarios=tuple(train_ids),
        )

    def sample_continuation(
        self,
        rng: np.random.Generator,
        *,
        now_s: float,
        shift_end_s: float,
        n_requests: int,
        prefix: str,
    ) -> list[Request]:
        """Sample future releases strictly after now_s, within remaining shift."""

        horizon = max(0.0, shift_end_s - now_s)
        if horizon <= 1.0 or n_requests <= 0:
            return []
        out: list[Request] = []
        for i in range(n_requests):
            # Uniform release in remaining horizon (training offsets only shape intensity)
            u = float(rng.random())
            release = now_s + u * horizon * 0.95
            node = int(rng.choice(self.snap_nodes))
            tw = float(rng.choice(self.tw_durations_s))
            svc = float(rng.choice(self.service_s))
            w = float(rng.choice(self.weights_kg))
            out.append(
                Request(
                    request_id=f"{prefix}-syn-{i}",
                    snap_node=node,
                    release_s=release,
                    tw_start_s=release,
                    tw_end_s=min(shift_end_s, release + tw),
                    service_s=svc,
                    weight_kg=w,
                    status=RequestStatus.UNRELEASED,
                )
            )
        return out
