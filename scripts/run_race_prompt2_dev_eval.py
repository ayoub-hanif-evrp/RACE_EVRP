#!/usr/bin/env python
"""Prompt 2: full development evaluation (60-scenario + ablations + robustness).

Does NOT touch evaluation_v1/locked_final.
Resumable via stable keys in race_prompt2_primary.csv / companion CSVs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from copy import deepcopy
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

OUT = ROOT / "data" / "casablanca" / "online_results" / "prompt2"
FIG = ROOT / "reports" / "figures" / "prompt2"

# Primary treatments
PRIMARY_D0 = [
    ("A_NONE_NOW", dict(comm_mode="none", assign_wait_mode="immediate", claim_mode="csc", send_claim_signals=False)),
    (
        "B_FULL_COMM",
        dict(
            comm_mode="full",
            assign_wait_mode="deadline_energy",
            peer_trust_mode="ttl_commitment",
            claim_mode="legacy",
            max_assign_wait_s=60.0,
        ),
    ),
    (
        "C_PERIODIC_COMM",
        dict(comm_mode="periodic", assign_wait_mode="immediate", claim_mode="legacy"),
    ),
    (
        "D_RANDOM_BYTE_MATCHED",
        dict(
            comm_mode="random_matched_bytes",
            assign_wait_mode="deadline_energy",
            peer_trust_mode="ttl_commitment",
            claim_mode="legacy",
            max_assign_wait_s=60.0,
        ),
    ),
    (
        "E_EVENT_TRIGGERED",
        dict(
            comm_mode="event_triggered",
            assign_wait_mode="deadline_energy",
            peer_trust_mode="ttl_commitment",
            claim_mode="legacy",
            max_assign_wait_s=60.0,
        ),
    ),
    (
        "F_SELECTIVE_LEGACY",
        dict(comm_mode="selective", assign_wait_mode="legacy", peer_trust_mode="ttl", claim_mode="legacy"),
    ),
    (
        "G_SELECTIVE_VALID_PEER",
        dict(
            comm_mode="selective",
            assign_wait_mode="deadline_energy",
            peer_trust_mode="ttl_commitment",
            claim_mode="legacy",
            max_assign_wait_s=60.0,
        ),
    ),
    (
        "H_CSC_LITE",
        dict(
            comm_mode="selective",
            claim_mode="csc",
            send_claim_signals=False,
            assign_wait_mode="deadline_energy",
            peer_trust_mode="ttl_commitment",
            wait_authority="decentralized_signal",
            max_assign_wait_s=60.0,
        ),
    ),
    (
        "I_MATCHED_WAIT_ZERO_COMM",
        dict(
            comm_mode="none",
            assign_wait_mode="deadline_energy",
            force_peer_wait_schedule=True,
            claim_mode="csc",
            send_claim_signals=False,
            wait_authority="decentralized_signal",
            max_assign_wait_s=60.0,
        ),
    ),
    (
        "J_MATCHED_WAIT_MESSAGE_PLACEBO",
        dict(
            comm_mode="selective",
            claim_mode="csc",
            send_claim_signals=False,
            assign_wait_mode="deadline_energy",
            peer_trust_mode="ttl_commitment",
            ignore_peer_bids=True,
            wait_authority="decentralized_signal",
            max_assign_wait_s=60.0,
        ),
    ),
]

# Positive-delay priority set
PRIMARY_DELAY = [
    "A_NONE_NOW",
    "B_FULL_COMM",
    "F_SELECTIVE_LEGACY",
    "G_SELECTIVE_VALID_PEER",
    "H_CSC_LITE",
    "I_MATCHED_WAIT_ZERO_COMM",
    "J_MATCHED_WAIT_MESSAGE_PLACEBO",
]

ABLATIONS = [
    (
        "ABL_A_CSC_NORMAL",
        dict(
            comm_mode="selective",
            claim_mode="csc",
            send_claim_signals=False,
            assign_wait_mode="deadline_energy",
            peer_trust_mode="ttl_commitment",
            wait_authority="decentralized_signal",
            max_assign_wait_s=60.0,
        ),
    ),
    (
        "ABL_A_CONTENT_WITHHELD",
        dict(
            comm_mode="selective",
            claim_mode="csc",
            send_claim_signals=False,
            assign_wait_mode="deadline_energy",
            peer_trust_mode="ttl_commitment",
            ignore_peer_bids=True,
            wait_authority="decentralized_signal",
            max_assign_wait_s=60.0,
        ),
    ),
    (
        "ABL_A_ZERO_COMM",
        dict(comm_mode="none", assign_wait_mode="immediate", claim_mode="csc", send_claim_signals=False),
    ),
    (
        "ABL_B_IMMEDIATE",
        dict(
            comm_mode="selective",
            claim_mode="csc",
            send_claim_signals=False,
            assign_wait_mode="immediate",
            peer_trust_mode="ttl_commitment",
        ),
    ),
    (
        "ABL_B_LEGACY_WAIT",
        dict(
            comm_mode="selective",
            claim_mode="csc",
            send_claim_signals=False,
            assign_wait_mode="legacy",
            peer_trust_mode="ttl_commitment",
        ),
    ),
    (
        "ABL_B_DEADLINE_WAIT",
        dict(
            comm_mode="selective",
            claim_mode="csc",
            send_claim_signals=False,
            assign_wait_mode="deadline_energy",
            peer_trust_mode="ttl_commitment",
            wait_authority="decentralized_signal",
            max_assign_wait_s=60.0,
        ),
    ),
    (
        "ABL_C_DEFER_VALID_OFFERS",
        dict(
            comm_mode="selective",
            claim_mode="legacy",
            assign_wait_mode="deadline_energy",
            peer_trust_mode="ttl_commitment",
            max_assign_wait_s=60.0,
        ),
    ),
    (
        "ABL_C_CSC_LITE",
        dict(
            comm_mode="selective",
            claim_mode="csc",
            send_claim_signals=False,
            assign_wait_mode="deadline_energy",
            peer_trust_mode="ttl_commitment",
            wait_authority="decentralized_signal",
            max_assign_wait_s=60.0,
        ),
    ),
    (
        "ABL_C_NO_PEER_DEFER",
        dict(
            comm_mode="selective",
            claim_mode="csc",
            send_claim_signals=False,
            ignore_peer_bids=True,
            assign_wait_mode="deadline_energy",
            peer_trust_mode="ttl_commitment",
            wait_authority="decentralized_signal",
            max_assign_wait_s=60.0,
        ),
    ),
    (
        "ABL_D_CONFIRM_ON",
        dict(
            comm_mode="selective",
            claim_mode="csc",
            send_claim_signals=True,
            assign_wait_mode="deadline_energy",
            peer_trust_mode="ttl_commitment",
            wait_authority="decentralized_signal",
            max_assign_wait_s=60.0,
        ),
    ),
    (
        "ABL_E_STRIP_PEER_ENERGY",
        dict(
            comm_mode="selective",
            claim_mode="csc",
            send_claim_signals=False,
            assign_wait_mode="deadline_energy",
            peer_trust_mode="ttl_commitment",
            wait_authority="decentralized_signal",
            strip_peer_energy_fields=True,
            max_assign_wait_s=60.0,
        ),
    ),
    (
        "ABL_F_NO_READINESS_CHARGE",
        dict(
            comm_mode="selective",
            claim_mode="csc",
            send_claim_signals=False,
            assign_wait_mode="deadline_energy",
            peer_trust_mode="ttl_commitment",
            wait_authority="decentralized_signal",
            enable_readiness_charge=False,
            max_assign_wait_s=60.0,
        ),
    ),
]


def config_hash(extra: dict, *, delay: float, loss: float, n_vehicles: int, soc: float) -> str:
    blob = json.dumps(
        {"extra": extra, "delay": delay, "loss": loss, "nv": n_vehicles, "soc": soc},
        sort_keys=True,
        default=str,
    )
    return hashlib.sha1(blob.encode()).hexdigest()[:12]


def run_key(scenario: str, treatment: str, delay: float, loss: float, n_vehicles: int, soc: float, ch: str) -> str:
    return f"{scenario}|{treatment}|d{delay}|l{loss}|nv{n_vehicles}|soc{soc}|{ch}"


def make_policy(extra: dict, *, delay: float, n_vehicles: int, matched_bytes: float | None):
    from race_casablanca.policies.race_cooperative import RaceCooperativePolicy

    kw = dict(
        rng_seed=7,
        enable_readiness_charge=True,
        fair_physical_decisions=True,
        message_delay_s=float(delay),
        matched_n_recipients=max(1, n_vehicles - 1),
    )
    # Extra overrides defaults (must not double-pass shared keys).
    kw.update({k: v for k, v in extra.items()})
    if kw.get("comm_mode") == "random_matched_bytes":
        mb = float(matched_bytes or 0.0)
        kw["matched_byte_budget"] = mb
        kw["typical_payload_bytes"] = max(200.0, mb / max(1, 2 * max(1, n_vehicles - 1)))
    return RaceCooperativePolicy(**kw)


def run_one(payload: dict) -> dict:
    from race_casablanca.coordination.experiment_metrics import extract_episode_row
    from race_casablanca.sim.environment import OnlineSimulator, SimConfig
    from race_casablanca.sim.scenario_loader import load_congestion_model, load_drive_graph, load_scenario
    from race_casablanca.sim.types import RequestStatus

    path = Path(payload["path"])
    label = payload["label"]
    extra = dict(payload["extra"])
    delay = float(payload["delay"])
    loss = float(payload.get("packet_loss_p", 0.0))
    n_vehicles = int(payload["n_vehicles"])
    soc = float(payload["soc"])
    matched_bytes = payload.get("matched_bytes")
    ch = payload["config_hash"]
    phase = payload.get("phase", "primary")

    try:
        graph = load_drive_graph()
        model = load_congestion_model()
        sc = load_scenario(path, load_network=False, graph=graph, model=model)
        reqs = deepcopy(sc.requests)
        for r in reqs:
            r.status = RequestStatus.UNRELEASED
            r.owner = None
        policy = make_policy(extra, delay=delay, n_vehicles=n_vehicles, matched_bytes=matched_bytes)
        t0 = time.time()
        sim = OnlineSimulator(
            scenario_id=f"{sc.scenario_id}/{label}/d{delay}/l{loss}",
            graph=graph,
            model=model,
            requests=reqs,
            fleet={**sc.fleet, "n_vehicles": n_vehicles},
            depot_node=sc.depot_node,
            shift_start_s=sc.shift_start_s,
            shift_end_s=sc.shift_end_s,
            config=SimConfig(
                info_mode="restricted",
                seed=0,
                initial_soc=soc,
                n_vehicles=n_vehicles,
                message_delay_s=delay,
                packet_loss_p=loss,
                decision_on_release=True,
                message_triggers_decision=True,
                periodic_state_broadcast=(extra.get("comm_mode") == "periodic"),
                day=str(getattr(sc, "day", "Monday")),
            ),
            policy=policy,
        )
        m = sim.run().to_dict()
        wall = time.time() - t0
        row = extract_episode_row(
            sim=sim,
            policy=policy,
            metrics=m,
            scenario=path.name,
            treatment=label,
            delay_s=delay,
            packet_loss_p=loss,
            n_vehicles=n_vehicles,
            soc=soc,
            config_hash=ch,
            wall_s=wall,
            extra={"phase": phase, "ok": True, "error": ""},
        )
        row["run_key"] = run_key(path.name, label, delay, loss, n_vehicles, soc, ch)
        return row
    except Exception as exc:  # noqa: BLE001 — record failure row
        return {
            "scenario": path.name,
            "treatment": label,
            "delay_s": delay,
            "packet_loss_p": loss,
            "n_vehicles": n_vehicles,
            "initial_soc": soc,
            "config_hash": ch,
            "phase": phase,
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(limit=5),
            "run_key": run_key(path.name, label, delay, loss, n_vehicles, soc, ch),
            "on_time_rate_all": float("nan"),
            "n_bid_attempted_bytes": 0.0,
            "owners_json": "{}",
        }


def calibrate_matched_bytes(train_paths: list[Path], *, n_vehicles: int, soc: float) -> float:
    """Predeclare selective attempted-byte budget on train scenarios (delay=0)."""

    bytes_list = []
    for p in train_paths:
        row = run_one(
            {
                "path": str(p),
                "label": "CAL_SELECTIVE",
                "extra": {
                    "comm_mode": "selective",
                    "claim_mode": "csc",
                    "send_claim_signals": False,
                    "assign_wait_mode": "deadline_energy",
                    "peer_trust_mode": "ttl_commitment",
                    "max_assign_wait_s": 60.0,
                },
                "delay": 0.0,
                "packet_loss_p": 0.0,
                "n_vehicles": n_vehicles,
                "soc": soc,
                "matched_bytes": None,
                "config_hash": "calibrate",
                "phase": "calibrate",
            }
        )
        if row.get("ok"):
            bytes_list.append(float(row["n_bid_attempted_bytes"]))
    return float(np.mean(bytes_list)) if bytes_list else 50000.0


def load_done_keys(csv_path: Path) -> set[str]:
    if not csv_path.exists():
        return set()
    try:
        df = pd.read_csv(csv_path)
    except Exception:
        return set()
    if "run_key" not in df.columns or "ok" not in df.columns:
        return set()
    ok = df[df["ok"].astype(str).isin(["True", "true", "1"])]
    return set(ok["run_key"].astype(str))


# Fixed schema so failure/success rows never misalign on append.
CSV_COLUMNS = [
    "run_key",
    "phase",
    "scenario",
    "treatment",
    "delay_s",
    "packet_loss_p",
    "n_vehicles",
    "initial_soc",
    "config_hash",
    "ok",
    "error",
    "n_requests",
    "n_on_time",
    "n_served",
    "n_missed",
    "n_expired",
    "n_rejected",
    "on_time_rate_all",
    "n_late_served",
    "energy_consumed_kwh",
    "energy_delivered_kwh",
    "charge_duration_s",
    "n_charges",
    "total_distance_m",
    "total_travel_s",
    "battery_reserve_violations",
    "battery_exhaustion",
    "planned_energy_rejections",
    "n_strandings",
    "mean_decision_runtime_s",
    "mean_decision_runtime_ms",
    "p50_decision_runtime_ms",
    "p95_decision_runtime_ms",
    "n_decisions",
    "n_bid_attempted_messages",
    "n_bid_attempted_bytes",
    "n_bid_dropped_messages",
    "n_bid_dropped_bytes",
    "n_bid_scheduled_messages",
    "n_bid_scheduled_bytes",
    "n_bid_delivered_messages",
    "n_bid_delivered_bytes",
    "n_bid_messages_legacy",
    "n_bid_bytes_legacy",
    "n_packets_dropped",
    "n_bid_delivers_superseded",
    "n_bid_delivers_coalesced",
    "mean_assign_wait_s",
    "sum_assign_wait_s",
    "n_assign_deferred",
    "n_assign_immediate",
    "n_claims_attempted",
    "n_claims_success",
    "n_defers_to_peer",
    "n_csc_safe_fallbacks",
    "n_speculative_offers_ignored",
    "n_counterfactual_decision_changes",
    "n_registry_dup_rejects",
    "wall_s",
    "owners_json",
]


def append_rows(csv_path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    normalized = []
    for r in rows:
        out = {c: r.get(c, "" if c in {"error", "owners_json", "phase", "run_key"} else 0) for c in CSV_COLUMNS}
        out["ok"] = bool(r.get("ok", False))
        out["error"] = str(r.get("error", "") or "")
        out["owners_json"] = str(r.get("owners_json", "{}") or "{}")
        normalized.append(out)
    df = pd.DataFrame(normalized, columns=CSV_COLUMNS)
    if csv_path.exists():
        df.to_csv(csv_path, mode="a", header=False, index=False)
    else:
        df.to_csv(csv_path, index=False)


def run_jobs(jobs: list[dict], csv_path: Path, *, workers: int, label: str) -> int:
    done = load_done_keys(csv_path)
    pending = [j for j in jobs if j["run_key"] not in done]
    print(f"{label}: {len(jobs)} declared, {len(done)} done, {len(pending)} pending", flush=True)
    if not pending:
        return 0
    n_ok = 0
    with ProcessPoolExecutor(max_workers=max(1, workers)) as ex:
        futs = {ex.submit(run_one, j): j for j in pending}
        batch: list[dict] = []
        finished = 0
        for fut in as_completed(futs):
            row = fut.result()
            batch.append(row)
            finished += 1
            if row.get("ok"):
                n_ok += 1
            if len(batch) >= 10 or finished == len(pending):
                append_rows(csv_path, batch)
                batch = []
            if finished % 20 == 0 or finished == len(pending):
                r = row
                print(
                    f"  [{label}] {finished}/{len(pending)} {r.get('scenario')} {r.get('treatment')} "
                    f"d={r.get('delay_s')} OT={r.get('on_time_rate_all')} "
                    f"E={r.get('energy_consumed_kwh')} ok={r.get('ok')}",
                    flush=True,
                )
    return n_ok


def build_primary_jobs(paths: list[Path], matched_bytes: float) -> list[dict]:
    jobs = []
    by_label = {k: v for k, v in PRIMARY_D0}
    for p in paths:
        for label, extra in PRIMARY_D0:
            ch = config_hash(extra, delay=0.0, loss=0.0, n_vehicles=3, soc=0.35)
            jobs.append(
                {
                    "path": str(p),
                    "label": label,
                    "extra": extra,
                    "delay": 0.0,
                    "packet_loss_p": 0.0,
                    "n_vehicles": 3,
                    "soc": 0.35,
                    "matched_bytes": matched_bytes,
                    "config_hash": ch,
                    "phase": "primary",
                    "run_key": run_key(p.name, label, 0.0, 0.0, 3, 0.35, ch),
                }
            )
        for delay in (15.0, 30.0, 120.0):
            for label in PRIMARY_DELAY:
                extra = by_label[label]
                ch = config_hash(extra, delay=delay, loss=0.0, n_vehicles=3, soc=0.35)
                jobs.append(
                    {
                        "path": str(p),
                        "label": label,
                        "extra": extra,
                        "delay": delay,
                        "packet_loss_p": 0.0,
                        "n_vehicles": 3,
                        "soc": 0.35,
                        "matched_bytes": matched_bytes,
                        "config_hash": ch,
                        "phase": "primary",
                        "run_key": run_key(p.name, label, delay, 0.0, 3, 0.35, ch),
                    }
                )
        # 10% loss pilot at 30s for key arms
        for label in ("A_NONE_NOW", "H_CSC_LITE", "G_SELECTIVE_VALID_PEER", "I_MATCHED_WAIT_ZERO_COMM"):
            extra = by_label[label]
            ch = config_hash(extra, delay=30.0, loss=0.10, n_vehicles=3, soc=0.35)
            jobs.append(
                {
                    "path": str(p),
                    "label": label,
                    "extra": extra,
                    "delay": 30.0,
                    "packet_loss_p": 0.10,
                    "n_vehicles": 3,
                    "soc": 0.35,
                    "matched_bytes": matched_bytes,
                    "config_hash": ch,
                    "phase": "primary_loss",
                    "run_key": run_key(p.name, label, 30.0, 0.10, 3, 0.35, ch),
                }
            )
    return jobs


def build_ablation_jobs(paths: list[Path]) -> list[dict]:
    jobs = []
    for p in paths:
        for delay in (0.0, 30.0):
            for label, extra in ABLATIONS:
                ch = config_hash(extra, delay=delay, loss=0.0, n_vehicles=3, soc=0.35)
                jobs.append(
                    {
                        "path": str(p),
                        "label": label,
                        "extra": extra,
                        "delay": delay,
                        "packet_loss_p": 0.0,
                        "n_vehicles": 3,
                        "soc": 0.35,
                        "matched_bytes": None,
                        "config_hash": ch,
                        "phase": "ablation",
                        "run_key": run_key(p.name, label, delay, 0.0, 3, 0.35, ch),
                    }
                )
    return jobs


def pick_balanced(paths: list[Path], n: int) -> list[Path]:
    groups = {"baseline": [], "peak_stress": [], "tight_windows": []}
    for p in paths:
        for g in groups:
            if p.name.startswith(g):
                groups[g].append(p)
                break
    out: list[Path] = []
    i = 0
    while len(out) < n:
        progressed = False
        for g in ("baseline", "peak_stress", "tight_windows"):
            if i < len(groups[g]) and len(out) < n:
                out.append(groups[g][i])
                progressed = True
        if not progressed:
            break
        i += 1
    return out


def build_scale_jobs(paths: list[Path]) -> list[dict]:
    jobs = []
    subset = pick_balanced(paths, 6)
    treatments = {
        "A_NONE_NOW": dict(comm_mode="none", assign_wait_mode="immediate", claim_mode="csc", send_claim_signals=False),
        "B_FULL_COMM": dict(
            comm_mode="full",
            assign_wait_mode="deadline_energy",
            peer_trust_mode="ttl_commitment",
            claim_mode="legacy",
            max_assign_wait_s=60.0,
        ),
        "G_SELECTIVE_VALID_PEER": dict(
            comm_mode="selective",
            assign_wait_mode="deadline_energy",
            peer_trust_mode="ttl_commitment",
            claim_mode="legacy",
            max_assign_wait_s=60.0,
        ),
        "H_CSC_LITE": dict(
            comm_mode="selective",
            claim_mode="csc",
            send_claim_signals=False,
            assign_wait_mode="deadline_energy",
            peer_trust_mode="ttl_commitment",
            wait_authority="decentralized_signal",
            max_assign_wait_s=60.0,
        ),
    }
    for p in subset:
        for nv in (3, 5, 10):
            for delay in (0.0, 30.0):
                for label, extra in treatments.items():
                    ch = config_hash(extra, delay=delay, loss=0.0, n_vehicles=nv, soc=0.35)
                    jobs.append(
                        {
                            "path": str(p),
                            "label": label,
                            "extra": extra,
                            "delay": delay,
                            "packet_loss_p": 0.0,
                            "n_vehicles": nv,
                            "soc": 0.35,
                            "matched_bytes": None,
                            "config_hash": ch,
                            "phase": "scale_fleet",
                            "run_key": run_key(p.name, label, delay, 0.0, nv, 0.35, ch),
                        }
                    )
        for soc in (0.35, 0.60, 1.0):
            for label in ("A_NONE_NOW", "H_CSC_LITE"):
                extra = treatments[label]
                ch = config_hash(extra, delay=0.0, loss=0.0, n_vehicles=3, soc=soc)
                jobs.append(
                    {
                        "path": str(p),
                        "label": label,
                        "extra": extra,
                        "delay": 0.0,
                        "packet_loss_p": 0.0,
                        "n_vehicles": 3,
                        "soc": soc,
                        "matched_bytes": None,
                        "config_hash": ch,
                        "phase": "scale_soc",
                        "run_key": run_key(p.name, label, 0.0, 0.0, 3, soc, ch),
                    }
                )
    return jobs


def paired_stats(df: pd.DataFrame, left: str, right: str, delay: float, loss: float = 0.0) -> dict:
    a = df[(df.treatment == left) & (df.delay_s == delay) & (df.packet_loss_p == loss) & (df.ok == True)].set_index(  # noqa: E712
        "scenario"
    )
    b = df[(df.treatment == right) & (df.delay_s == delay) & (df.packet_loss_p == loss) & (df.ok == True)].set_index(  # noqa: E712
        "scenario"
    )
    common = sorted(set(a.index) & set(b.index))
    if len(common) < 2:
        return {"left": left, "right": right, "delay_s": delay, "n": len(common)}
    d = a.loc[common, "on_time_rate_all"].astype(float) - b.loc[common, "on_time_rate_all"].astype(float)
    # paired bootstrap CI
    rng = np.random.default_rng(0)
    boots = []
    vals = d.to_numpy()
    for _ in range(2000):
        samp = rng.choice(vals, size=len(vals), replace=True)
        boots.append(float(np.mean(samp)))
    lo, hi = np.quantile(boots, [0.025, 0.975])
    wins = int(np.sum(vals > 1e-12))
    losses = int(np.sum(vals < -1e-12))
    ties = int(len(vals) - wins - losses)
    db = a.loc[common, "n_bid_attempted_bytes"].astype(float) - b.loc[common, "n_bid_attempted_bytes"].astype(float)
    hamm = []
    for s in common:
        da = json.loads(a.loc[s, "owners_json"] or "{}")
        dbj = json.loads(b.loc[s, "owners_json"] or "{}")
        keys = set(da) | set(dbj)
        hamm.append(sum(1 for k in keys if da.get(k) != dbj.get(k)))
    return {
        "left": left,
        "right": right,
        "delay_s": delay,
        "packet_loss_p": loss,
        "n": len(common),
        "mean_left_ot": float(a.loc[common, "on_time_rate_all"].mean()),
        "mean_right_ot": float(b.loc[common, "on_time_rate_all"].mean()),
        "mean_delta_ot_pp": float(d.mean() * 100),
        "ci95_lo_pp": float(lo * 100),
        "ci95_hi_pp": float(hi * 100),
        "wins": wins,
        "ties": ties,
        "losses": losses,
        "mean_delta_attempted_bytes": float(db.mean()),
        "mean_owner_hamming": float(np.mean(hamm)),
        "n_owner_diff_scenarios": int(sum(1 for h in hamm if h > 0)),
        "mean_left_energy_kwh": float(a.loc[common, "energy_consumed_kwh"].mean()),
        "mean_right_energy_kwh": float(b.loc[common, "energy_consumed_kwh"].mean()),
        "mean_left_decision_ms": float(a.loc[common, "mean_decision_runtime_ms"].mean()),
        "mean_right_decision_ms": float(b.loc[common, "mean_decision_runtime_ms"].mean()),
    }


def summarize_and_figures(primary_csv: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    FIG.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(primary_csv)
    if "ok" in df.columns:
        df["ok"] = df["ok"].astype(str).isin(["True", "true", "1"])
        df = df[df.ok].copy()
    summary = (
        df.groupby(["treatment", "delay_s", "packet_loss_p"], as_index=False)
        .agg(
            n=("scenario", "nunique"),
            mean_ot=("on_time_rate_all", "mean"),
            std_ot=("on_time_rate_all", "std"),
            mean_attempted_bytes=("n_bid_attempted_bytes", "mean"),
            mean_delivered_bytes=("n_bid_delivered_bytes", "mean"),
            mean_energy=("energy_consumed_kwh", "mean"),
            mean_charge_kwh=("energy_delivered_kwh", "mean"),
            mean_charges=("n_charges", "mean"),
            mean_dist_m=("total_distance_m", "mean"),
            mean_decision_ms=("mean_decision_runtime_ms", "mean"),
            sum_reserve=("battery_reserve_violations", "sum"),
            sum_exhaust=("battery_exhaustion", "sum"),
            sum_strand=("n_strandings", "sum"),
        )
        .sort_values(["packet_loss_p", "delay_s", "treatment"])
    )
    summary.to_csv(OUT / "race_prompt2_primary_summary.csv", index=False)

    paired = []
    for delay in sorted(df.delay_s.unique()):
        for left, right in [
            ("H_CSC_LITE", "A_NONE_NOW"),
            ("H_CSC_LITE", "I_MATCHED_WAIT_ZERO_COMM"),
            ("H_CSC_LITE", "J_MATCHED_WAIT_MESSAGE_PLACEBO"),
            ("H_CSC_LITE", "B_FULL_COMM"),
            ("H_CSC_LITE", "G_SELECTIVE_VALID_PEER"),
            ("H_CSC_LITE", "F_SELECTIVE_LEGACY"),
            ("G_SELECTIVE_VALID_PEER", "I_MATCHED_WAIT_ZERO_COMM"),
            ("B_FULL_COMM", "A_NONE_NOW"),
            ("J_MATCHED_WAIT_MESSAGE_PLACEBO", "I_MATCHED_WAIT_ZERO_COMM"),
        ]:
            if left in set(df.treatment) and right in set(df.treatment):
                paired.append(paired_stats(df, left, right, float(delay), 0.0))
    if (df.packet_loss_p == 0.1).any():
        paired.append(paired_stats(df, "H_CSC_LITE", "I_MATCHED_WAIT_ZERO_COMM", 30.0, 0.1))
    (OUT / "race_prompt2_primary_paired.json").write_text(json.dumps(paired, indent=2), encoding="utf-8")

    # Pareto: OT vs attempted bytes at delay 0 and 30
    for delay in (0.0, 30.0):
        sub = summary[(summary.delay_s == delay) & (summary.packet_loss_p == 0.0)]
        if sub.empty:
            continue
        fig, ax = plt.subplots(figsize=(7, 5))
        ax.scatter(sub.mean_attempted_bytes, sub.mean_ot * 100)
        for _, r in sub.iterrows():
            ax.annotate(r.treatment.replace("_", "\n"), (r.mean_attempted_bytes, r.mean_ot * 100), fontsize=7)
        ax.set_xlabel("Mean attempted recipient bid bytes")
        ax.set_ylabel("Mean on-time rate (%)")
        ax.set_title(f"Service–communication Pareto (delay={int(delay)}s)")
        ax.grid(True, alpha=0.3)
        fig.tight_layout()
        fig.savefig(FIG / f"pareto_delay_{int(delay)}.png", dpi=150)
        plt.close(fig)

    # Regime breakdown for H vs A at delay 0
    def regime(name: str) -> str:
        if name.startswith("baseline"):
            return "baseline"
        if name.startswith("peak"):
            return "peak_stress"
        if name.startswith("tight"):
            return "tight_windows"
        return "other"

    df["regime"] = df.scenario.map(regime)
    reg = (
        df[(df.packet_loss_p == 0) & (df.treatment.isin(["H_CSC_LITE", "A_NONE_NOW", "B_FULL_COMM", "G_SELECTIVE_VALID_PEER"]))]
        .groupby(["regime", "treatment", "delay_s"], as_index=False)
        .agg(mean_ot=("on_time_rate_all", "mean"), n=("scenario", "count"))
    )
    reg.to_csv(OUT / "race_prompt2_regime_summary.csv", index=False)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--limit-scenarios", type=int, default=0)
    parser.add_argument("--skip-primary", action="store_true")
    parser.add_argument("--skip-ablations", action="store_true")
    parser.add_argument("--skip-scale", action="store_true")
    parser.add_argument("--phase", choices=["all", "primary", "ablations", "scale", "analyze"], default="all")
    args = parser.parse_args()

    from race_casablanca.paths import project_root, scenarios_dir

    OUT.mkdir(parents=True, exist_ok=True)
    FIG.mkdir(parents=True, exist_ok=True)

    # Guard: never touch locked_final
    locked = project_root() / "data" / "casablanca" / "evaluation_v1" / "locked_final"
    assert "locked_final" not in str(OUT.resolve())
    print(f"locked_final path exists={locked.exists()} (NOT USED)", flush=True)

    train_paths = [p for p in sorted((scenarios_dir() / "train").iterdir()) if p.is_dir()][:8]
    print("Calibrating matched bytes on train...", flush=True)
    matched_bytes = calibrate_matched_bytes(train_paths, n_vehicles=3, soc=0.35)
    print(f"matched_bytes={matched_bytes:.1f}", flush=True)
    (OUT / "race_prompt2_matched_budget.json").write_text(
        json.dumps(
            {
                "matched_attempted_bytes_mean_train": matched_bytes,
                "calibrated_on": [p.name for p in train_paths],
                "delay_s": 0.0,
                "note": "Budget from selective CSC-lite attempted bytes; declared before primary runs.",
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    exp = project_root() / "data" / "casablanca" / "evaluation_v1" / "default"
    paths = sorted([p for p in exp.iterdir() if p.is_dir()])
    if args.limit_scenarios > 0:
        paths = paths[: args.limit_scenarios]
    print(f"Development scenarios: {len(paths)}", flush=True)

    primary_csv = OUT / "race_prompt2_primary.csv"
    ablation_csv = OUT / "race_prompt2_ablations.csv"
    scale_csv = OUT / "race_prompt2_scale.csv"

    if args.phase in ("all", "primary") and not args.skip_primary:
        jobs = build_primary_jobs(paths, matched_bytes)
        (OUT / "race_prompt2_primary_manifest.json").write_text(
            json.dumps(
                {
                    "n_jobs": len(jobs),
                    "n_scenarios": len(paths),
                    "treatments_d0": [t[0] for t in PRIMARY_D0],
                    "treatments_delay": PRIMARY_DELAY,
                    "delays": [0, 15, 30, 120],
                    "matched_bytes": matched_bytes,
                    "locked_final_used": False,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        run_jobs(jobs, primary_csv, workers=args.workers, label="primary")

    if args.phase in ("all", "ablations") and not args.skip_ablations:
        jobs = build_ablation_jobs(paths)
        run_jobs(jobs, ablation_csv, workers=args.workers, label="ablations")

    if args.phase in ("all", "scale") and not args.skip_scale:
        jobs = build_scale_jobs(paths)
        run_jobs(jobs, scale_csv, workers=args.workers, label="scale")

    if args.phase in ("all", "analyze") or True:
        if primary_csv.exists():
            summarize_and_figures(primary_csv)
            print("Wrote summaries and figures.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
