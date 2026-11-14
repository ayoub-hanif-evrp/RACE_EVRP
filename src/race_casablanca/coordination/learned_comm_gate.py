"""Lightweight send/suppress gate for RACE-CERT (communication only)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

from race_casablanca.coordination.selective_protocol import BidMemory, selective_should_send
from race_casablanca.coordination.task_bids import TaskBid
from race_casablanca.policies.race_cert_hybrid import RaceCertHybridPolicy
from race_casablanca.policies.race_cooperative import RaceCooperativePolicy


FEAT_DIM = 9


class TinyCommGate(nn.Module):
    def __init__(self, hidden: int = 32):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(FEAT_DIM, hidden),
            nn.ReLU(),
            nn.Linear(hidden, 2),  # suppress, send
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


def gate_send_fn(model: TinyCommGate, *, device: str = "cpu"):
    model = model.to(device)
    model.eval()

    def _fn(own, peers, mem, now_s, feat) -> tuple[bool, str]:
        with torch.no_grad():
            x = torch.as_tensor(feat, dtype=torch.float32, device=device).unsqueeze(0)
            logits = model(x)
            send = bool(int(logits.argmax(-1).item()) == 1)
        return send, "learned_send" if send else "learned_suppress"

    return _fn


def train_gate_bc(
    X: np.ndarray,
    y: np.ndarray,
    *,
    epochs: int = 80,
    lr: float = 1e-2,
    device: str = "cpu",
) -> TinyCommGate:
    model = TinyCommGate().to(device)
    opt = torch.optim.Adam(model.parameters(), lr=lr)
    xt = torch.as_tensor(X, dtype=torch.float32, device=device)
    yt = torch.as_tensor(y, dtype=torch.int64, device=device)
    # class weight
    counts = np.bincount(y, minlength=2).astype(np.float32)
    w = counts.sum() / (counts + 1.0)
    w = w / w.mean()
    wt = torch.as_tensor(w, dtype=torch.float32, device=device)
    model.train()
    for _ in range(epochs):
        logits = model(xt)
        loss = F.cross_entropy(logits, yt, weight=wt)
        opt.zero_grad()
        loss.backward()
        opt.step()
    model.eval()
    return model


def collect_selective_labels(env_run_fn) -> tuple[np.ndarray, np.ndarray]:
    """env_run_fn should yield (feat, send_label) pairs via callback — unused helper."""

    raise NotImplementedError


def collect_from_policy_rollouts(
    run_episode_fn,
    scenarios,
    *,
    n_vehicles: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Collect BC labels by mirroring selective_should_send on hybrid features."""

    xs: list[list[float]] = []
    ys: list[int] = []

    class _LabelCollector(RaceCertHybridPolicy):
        def _maybe_communicate(self, obs, actions, own_bids, reason):
            n_peers = self._n_announced_peers(obs)
            for rid, own in own_bids.items():
                peers = self._peer_bids_for(obs, rid)
                mem = self._sent.get((obs.vehicle_id, rid))
                feat = self._comm_features(own, peers, mem, float(obs.now_s), n_peers)
                send, _kind = selective_should_send(own, peers, mem, now_s=float(obs.now_s))
                xs.append(feat)
                ys.append(1 if send else 0)
            # Execute selective communication for an on-policy selective trajectory.
            saved = self.comm_mode
            self.comm_mode = "selective"
            RaceCooperativePolicy._maybe_communicate(self, obs, actions, own_bids, reason)
            self.comm_mode = saved

    for sc in scenarios:
        pol = _LabelCollector(comm_mode="learned", rng_seed=7)
        run_episode_fn(sc, pol, n_vehicles=n_vehicles)
    if not xs:
        return np.zeros((0, FEAT_DIM), dtype=np.float32), np.zeros((0,), dtype=np.int64)
    return np.asarray(xs, dtype=np.float32), np.asarray(ys, dtype=np.int64)


def save_gate(model: TinyCommGate, path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    torch.save({"state_dict": model.state_dict(), "feat_dim": FEAT_DIM}, path)


def load_gate(path: Path, *, device: str = "cpu") -> TinyCommGate:
    blob = torch.load(Path(path), map_location=device, weights_only=False)
    model = TinyCommGate()
    model.load_state_dict(blob["state_dict"])
    return model.to(device)
