#!/usr/bin/env python
"""Prompt 3: preflight comparator fixes + locked_final 720-run evaluation.

CSC-lite parameters are frozen. Only comparator implementations may differ from Prompt 2.
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

OUT = ROOT / "data" / "casablanca" / "online_results" / "final_locked"
PREFLIGHT = ROOT / "data" / "casablanca" / "online_results" / "prompt3_preflight"
FIG = ROOT / "reports" / "figures" / "final_locked"

PERIODIC_S = 300.0
SOURCE_IMPL_SHA = "deb750af7edebdc8868eed2af6fa389e77765136"

CSC_LITE = dict(
    comm_mode="selective",
    claim_mode="csc",
    send_claim_signals=False,
    assign_wait_mode="deadline_energy",
    peer_trust_mode="ttl_commitment",
    wait_authority="decentralized_signal",
    fair_physical_decisions=True,
    max_assign_wait_s=60.0,
    urgency_slack_s=180.0,
    bid_ttl_s=180.0,
    enable_readiness_charge=True,
    charge_target_soc=0.70,
    ignore_peer_bids=False,
    force_peer_wait_schedule=False,
    delay_aware_trust=False,
)

TREATMENTS = {
    "A_NONE_NOW": dict(comm_mode="none", assign_wait_mode="immediate", claim_mode="csc", send_claim_signals=False),
    "B_FULL_COMM": dict(
        comm_mode="full",
        assign_wait_mode="deadline_energy",
        peer_trust_mode="ttl_commitment",
        claim_mode="legacy",
        max_assign_wait_s=60.0,
    ),
    "C_PERIODIC_COMM": dict(comm_mode="periodic", assign_wait_mode="immediate", claim_mode="legacy"),
    "D_RANDOM_BYTE_MATCHED": dict(
        comm_mode="random_matched_bytes",
        assign_wait_mode="deadline_energy",
        peer_trust_mode="ttl_commitment",
        claim_mode="legacy",
        max_assign_wait_s=60.0,
    ),
    "E_EVENT_TRIGGERED": dict(
        comm_mode="event_triggered",
        assign_wait_mode="deadline_energy",
        peer_trust_mode="ttl_commitment",
        claim_mode="legacy",
        max_assign_wait_s=60.0,
    ),
    "F_SELECTIVE_LEGACY": dict(
        comm_mode="selective", assign_wait_mode="legacy", peer_trust_mode="ttl", claim_mode="legacy"
    ),
    "G_SELECTIVE_VALID_PEER": dict(
        comm_mode="selective",
        assign_wait_mode="deadline_energy",
        peer_trust_mode="ttl_commitment",
        claim_mode="legacy",
        max_assign_wait_s=60.0,
    ),
    "H_CSC_LITE": dict(CSC_LITE),
    "I_MATCHED_WAIT_ZERO_COMM": dict(
        comm_mode="none",
        assign_wait_mode="deadline_energy",
        force_peer_wait_schedule=True,
        claim_mode="csc",
        send_claim_signals=False,
        wait_authority="decentralized_signal",
        max_assign_wait_s=60.0,
    ),
    "J_MATCHED_WAIT_MESSAGE_PLACEBO": dict(
        comm_mode="selective",
        claim_mode="csc",
        send_claim_signals=False,
        assign_wait_mode="deadline_energy",
        peer_trust_mode="ttl_commitment",
        ignore_peer_bids=True,
        wait_authority="decentralized_signal",
        max_assign_wait_s=60.0,
    ),
}

ZERO_DELAY = list(TREATMENTS.keys())
DELAY_TREATMENTS = [
    "A_NONE_NOW",
    "B_FULL_COMM",
    "F_SELECTIVE_LEGACY",
    "G_SELECTIVE_VALID_PEER",
    "H_CSC_LITE",
    "I_MATCHED_WAIT_ZERO_COMM",
    "J_MATCHED_WAIT_MESSAGE_PLACEBO",
]

CSV_COLUMNS = [
    "run_key",
    "phase",
    "scenario",
    "regime",
    "treatment",
    "delay_s",
    "packet_loss_p",
    "n_vehicles",
    "initial_soc",
    "config_hash",
    "source_sha",
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
    "periodic_broadcast_s",
    "matched_byte_budget",
    "wall_s",
    "owners_json",
]


def regime_of(name: str) -> str:
    if name.startswith("baseline"):
        return "baseline"
    if name.startswith("peak"):
        return "peak_stress"
    if name.startswith("tight"):
        return "tight_windows"
    return "other"


def config_hash(extra: dict, *, delay: float, loss: float, n_vehicles: int, soc: float, matched: float, periodic_s: float) -> str:
    blob = json.dumps(
        {
            "extra": extra,
            "delay": delay,
            "loss": loss,
            "nv": n_vehicles,
            "soc": soc,
            "matched": matched,
            "periodic_s": periodic_s,
        },
        sort_keys=True,
        default=str,
    )
    return hashlib.sha1(blob.encode()).hexdigest()[:12]


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def make_policy(extra: dict, *, delay: float, n_vehicles: int, matched_bytes: float | None):
    from race_casablanca.policies.race_cooperative import RaceCooperativePolicy

    kw = dict(
        rng_seed=7,
        enable_readiness_charge=True,
        fair_physical_decisions=True,
        message_delay_s=float(delay),
        matched_n_recipients=max(1, n_vehicles - 1),
    )
    kw.update(dict(extra))
    if kw.get("comm_mode") == "random_matched_bytes":
        mb = float(matched_bytes or 0.0)
        kw["matched_byte_budget"] = mb
        # Fallback estimate only; runtime charges actual serialized sizes.
        kw["typical_payload_bytes"] = 220.0
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
    periodic_s = float(payload.get("periodic_broadcast_s", 0.0))
    ch = payload["config_hash"]
    phase = payload.get("phase", "locked")
    source_sha = payload.get("source_sha", "")

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
        is_periodic = extra.get("comm_mode") == "periodic"
        sim = OnlineSimulator(
            scenario_id=f"{sc.scenario_id}/{label}/d{delay}",
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
                periodic_broadcast_s=float(periodic_s if is_periodic else 0.0),
                periodic_state_broadcast=False,
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
            extra={
                "phase": phase,
                "ok": True,
                "error": "",
                "regime": regime_of(path.name),
                "source_sha": source_sha,
                "periodic_broadcast_s": float(sim.config.periodic_broadcast_s),
                "matched_byte_budget": float(matched_bytes or 0.0),
                "n_bid_messages_legacy": float(getattr(sim, "n_bid_messages", 0) or 0),
                "n_bid_bytes_legacy": float(getattr(sim, "n_bid_bytes", 0) or 0),
            },
        )
        row["run_key"] = payload["run_key"]
        return row
    except Exception as exc:  # noqa: BLE001
        return {
            "run_key": payload["run_key"],
            "phase": phase,
            "scenario": path.name,
            "regime": regime_of(path.name),
            "treatment": label,
            "delay_s": delay,
            "packet_loss_p": loss,
            "n_vehicles": n_vehicles,
            "initial_soc": soc,
            "config_hash": ch,
            "source_sha": source_sha,
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(limit=4),
            "on_time_rate_all": float("nan"),
            "n_bid_attempted_bytes": 0.0,
            "owners_json": "{}",
            "periodic_broadcast_s": periodic_s,
            "matched_byte_budget": float(matched_bytes or 0.0),
        }


def append_rows(csv_path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    normalized = []
    for r in rows:
        out = {c: r.get(c, "" if c in {"error", "owners_json", "phase", "run_key", "regime", "source_sha", "treatment", "scenario"} else 0) for c in CSV_COLUMNS}
        out["ok"] = bool(r.get("ok", False))
        out["error"] = str(r.get("error", "") or "")
        out["owners_json"] = str(r.get("owners_json", "{}") or "{}")
        normalized.append(out)
    df = pd.DataFrame(normalized, columns=CSV_COLUMNS)
    if csv_path.exists():
        df.to_csv(csv_path, mode="a", header=False, index=False)
    else:
        df.to_csv(csv_path, index=False)


def load_done(csv_path: Path) -> set[str]:
    if not csv_path.exists():
        return set()
    df = pd.read_csv(csv_path)
    if "run_key" not in df.columns or "ok" not in df.columns:
        return set()
    ok = df[df["ok"].astype(str).isin(["True", "true", "1"])]
    return set(ok["run_key"].astype(str))


def run_jobs(jobs: list[dict], csv_path: Path, *, workers: int, label: str) -> int:
    done = load_done(csv_path)
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
            if len(batch) >= 8 or finished == len(pending):
                append_rows(csv_path, batch)
                batch = []
            if finished % 15 == 0 or finished == len(pending):
                r = row
                print(
                    f"  [{label}] {finished}/{len(pending)} {r.get('scenario')} {r.get('treatment')} "
                    f"d={r.get('delay_s')} OT={r.get('on_time_rate_all')} bytes={r.get('n_bid_attempted_bytes')} ok={r.get('ok')}",
                    flush=True,
                )
    return n_ok


def calibrate(train_paths: list[Path]) -> dict:
    PREFLIGHT.mkdir(parents=True, exist_ok=True)
    csc_rows = []
    for p in train_paths:
        ch = config_hash(CSC_LITE, delay=0.0, loss=0.0, n_vehicles=3, soc=0.35, matched=0.0, periodic_s=0.0)
        row = run_one(
            {
                "path": str(p),
                "label": "H_CSC_LITE",
                "extra": CSC_LITE,
                "delay": 0.0,
                "packet_loss_p": 0.0,
                "n_vehicles": 3,
                "soc": 0.35,
                "matched_bytes": None,
                "periodic_broadcast_s": 0.0,
                "config_hash": ch,
                "phase": "calibrate_csc",
                "source_sha": SOURCE_IMPL_SHA,
                "run_key": f"cal|{p.name}|H|d0",
            }
        )
        csc_rows.append(row)
    csc_df = pd.DataFrame(csc_rows)
    csc_df.to_csv(PREFLIGHT / "train_csc_lite_calibration.csv", index=False)
    target = float(csc_df[csc_df.ok == True]["n_bid_attempted_bytes"].mean())  # noqa: E712

    rand_rows = []
    for p in train_paths:
        extra = TREATMENTS["D_RANDOM_BYTE_MATCHED"]
        ch = config_hash(extra, delay=0.0, loss=0.0, n_vehicles=3, soc=0.35, matched=target, periodic_s=0.0)
        row = run_one(
            {
                "path": str(p),
                "label": "D_RANDOM_BYTE_MATCHED",
                "extra": extra,
                "delay": 0.0,
                "packet_loss_p": 0.0,
                "n_vehicles": 3,
                "soc": 0.35,
                "matched_bytes": target,
                "periodic_broadcast_s": 0.0,
                "config_hash": ch,
                "phase": "calibrate_random",
                "source_sha": SOURCE_IMPL_SHA,
                "run_key": f"cal|{p.name}|D|d0",
            }
        )
        rand_rows.append(row)
    rand_df = pd.DataFrame(rand_rows)
    rand_df.to_csv(PREFLIGHT / "train_random_matched_calibration.csv", index=False)
    achieved = float(rand_df[rand_df.ok == True]["n_bid_attempted_bytes"].mean())  # noqa: E712
    ratio = achieved / target if target > 0 else float("nan")

    per_rows = []
    for p in train_paths:
        extra = TREATMENTS["C_PERIODIC_COMM"]
        ch = config_hash(extra, delay=0.0, loss=0.0, n_vehicles=3, soc=0.35, matched=0.0, periodic_s=PERIODIC_S)
        row = run_one(
            {
                "path": str(p),
                "label": "C_PERIODIC_COMM",
                "extra": extra,
                "delay": 0.0,
                "packet_loss_p": 0.0,
                "n_vehicles": 3,
                "soc": 0.35,
                "matched_bytes": None,
                "periodic_broadcast_s": PERIODIC_S,
                "config_hash": ch,
                "phase": "calibrate_periodic",
                "source_sha": SOURCE_IMPL_SHA,
                "run_key": f"cal|{p.name}|C|d0",
            }
        )
        per_rows.append(row)
    per_df = pd.DataFrame(per_rows)
    per_df.to_csv(PREFLIGHT / "train_periodic_calibration.csv", index=False)

    summary = {
        "train_scenarios": [p.name for p in train_paths],
        "csc_lite_mean_attempted_bytes": target,
        "random_matched_budget": target,
        "random_matched_mean_attempted_bytes": achieved,
        "random_matched_ratio_to_csc": ratio,
        "periodic_broadcast_s": PERIODIC_S,
        "periodic_mean_attempted_bytes": float(per_df[per_df.ok == True]["n_bid_attempted_bytes"].mean()),  # noqa: E712
        "periodic_n_positive_byte_episodes": int((per_df["n_bid_attempted_bytes"] > 0).sum()),
    }
    (PREFLIGHT / "calibration_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)
    return summary


def freeze_check(dev_paths: list[Path], prompt2_csv: Path) -> dict:
    """Reproduce CSC-lite on a few development scenarios vs Prompt 2 table."""
    ref = pd.read_csv(prompt2_csv)
    ref = ref[(ref.treatment == "H_CSC_LITE") & (ref.delay_s == 0.0) & (ref.packet_loss_p == 0.0)]
    rows = []
    for p in dev_paths:
        ch = config_hash(CSC_LITE, delay=0.0, loss=0.0, n_vehicles=3, soc=0.35, matched=0.0, periodic_s=0.0)
        row = run_one(
            {
                "path": str(p),
                "label": "H_CSC_LITE",
                "extra": CSC_LITE,
                "delay": 0.0,
                "packet_loss_p": 0.0,
                "n_vehicles": 3,
                "soc": 0.35,
                "matched_bytes": None,
                "periodic_broadcast_s": 0.0,
                "config_hash": ch,
                "phase": "freeze_check",
                "source_sha": SOURCE_IMPL_SHA,
                "run_key": f"freeze|{p.name}|H|d0",
            }
        )
        prev = ref[ref.scenario == p.name]
        prev_ot = float(prev.on_time_rate_all.iloc[0]) if len(prev) else float("nan")
        row["prompt2_ot"] = prev_ot
        row["delta_ot"] = float(row.get("on_time_rate_all", float("nan"))) - prev_ot
        rows.append(row)
    df = pd.DataFrame(rows)
    df.to_csv(PREFLIGHT / "csc_freeze_check.csv", index=False)
    max_abs = float(np.nanmax(np.abs(df["delta_ot"].to_numpy()))) if len(df) else float("nan")
    out = {"n": len(df), "max_abs_delta_ot": max_abs, "pass": bool(max_abs < 1e-9)}
    (PREFLIGHT / "csc_freeze_check_summary.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print("freeze_check", out, flush=True)
    return out


def build_locked_jobs(paths: list[Path], matched_bytes: float, source_sha: str) -> list[dict]:
    jobs = []
    for p in paths:
        for label in ZERO_DELAY:
            extra = TREATMENTS[label]
            periodic_s = PERIODIC_S if label == "C_PERIODIC_COMM" else 0.0
            ch = config_hash(
                extra, delay=0.0, loss=0.0, n_vehicles=3, soc=0.35, matched=matched_bytes, periodic_s=periodic_s
            )
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
                    "periodic_broadcast_s": periodic_s,
                    "config_hash": ch,
                    "phase": "locked",
                    "source_sha": source_sha,
                    "run_key": f"{p.name}|{label}|d0.0|l0.0|nv3|soc0.35|{ch}",
                }
            )
        for delay in (30.0, 120.0):
            for label in DELAY_TREATMENTS:
                extra = TREATMENTS[label]
                ch = config_hash(
                    extra, delay=delay, loss=0.0, n_vehicles=3, soc=0.35, matched=matched_bytes, periodic_s=0.0
                )
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
                        "periodic_broadcast_s": 0.0,
                        "config_hash": ch,
                        "phase": "locked",
                        "source_sha": source_sha,
                        "run_key": f"{p.name}|{label}|d{delay}|l0.0|nv3|soc0.35|{ch}",
                    }
                )
    return jobs


def paired_stats(df: pd.DataFrame, left: str, right: str, delay: float) -> dict:
    a = df[(df.treatment == left) & (df.delay_s == delay) & (df.ok == True)].set_index("scenario")  # noqa: E712
    b = df[(df.treatment == right) & (df.delay_s == delay) & (df.ok == True)].set_index("scenario")  # noqa: E712
    common = sorted(set(a.index) & set(b.index))
    if len(common) < 2:
        return {"left": left, "right": right, "delay_s": delay, "n": len(common)}
    d = a.loc[common, "on_time_rate_all"].astype(float) - b.loc[common, "on_time_rate_all"].astype(float)
    rng = np.random.default_rng(0)
    vals = d.to_numpy()
    boots = [float(np.mean(rng.choice(vals, size=len(vals), replace=True))) for _ in range(2000)]
    lo, hi = np.quantile(boots, [0.025, 0.975])
    # one-sided 5% lower bound for noninferiority vs full (approx 5th percentile of bootstrap)
    lo_onesided = float(np.quantile(boots, 0.05))
    wins = int(np.sum(vals > 1e-12))
    losses = int(np.sum(vals < -1e-12))
    ties = len(vals) - wins - losses
    db = a.loc[common, "n_bid_attempted_bytes"].astype(float) - b.loc[common, "n_bid_attempted_bytes"].astype(float)
    hamm = []
    for s in common:
        da = json.loads(a.loc[s, "owners_json"] or "{}")
        dbj = json.loads(b.loc[s, "owners_json"] or "{}")
        keys = set(da) | set(dbj)
        hamm.append(sum(1 for k in keys if da.get(k) != dbj.get(k)))
    mean_left_b = float(a.loc[common, "n_bid_attempted_bytes"].mean())
    mean_right_b = float(b.loc[common, "n_bid_attempted_bytes"].mean())
    return {
        "left": left,
        "right": right,
        "delay_s": delay,
        "n": len(common),
        "mean_left_ot": float(a.loc[common, "on_time_rate_all"].mean()),
        "mean_right_ot": float(b.loc[common, "on_time_rate_all"].mean()),
        "mean_delta_ot_pp": float(d.mean() * 100),
        "ci95_lo_pp": float(lo * 100),
        "ci95_hi_pp": float(hi * 100),
        "onesided05_lower_pp": float(lo_onesided * 100),
        "wins": wins,
        "ties": ties,
        "losses": losses,
        "mean_left_attempted_bytes": mean_left_b,
        "mean_right_attempted_bytes": mean_right_b,
        "byte_ratio_means": (mean_left_b / mean_right_b) if mean_right_b > 0 else float("nan"),
        "mean_delta_attempted_bytes": float(db.mean()),
        "mean_owner_hamming": float(np.mean(hamm)),
        "n_owner_diff_scenarios": int(sum(1 for h in hamm if h > 0)),
        "mean_left_energy_kwh": float(a.loc[common, "energy_consumed_kwh"].mean()),
        "mean_right_energy_kwh": float(b.loc[common, "energy_consumed_kwh"].mean()),
        "mean_left_decision_ms": float(a.loc[common, "mean_decision_runtime_ms"].mean()),
        "mean_right_decision_ms": float(b.loc[common, "mean_decision_runtime_ms"].mean()),
    }


def analyze(csv_path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    FIG.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(csv_path)
    df["ok"] = df["ok"].astype(str).isin(["True", "true", "1"])
    ok = df[df.ok].copy()
    summary = (
        ok.groupby(["treatment", "delay_s"], as_index=False)
        .agg(
            n=("scenario", "nunique"),
            mean_ot=("on_time_rate_all", "mean"),
            std_ot=("on_time_rate_all", "std"),
            mean_attempted_bytes=("n_bid_attempted_bytes", "mean"),
            mean_delivered_bytes=("n_bid_delivered_bytes", "mean"),
            mean_energy=("energy_consumed_kwh", "mean"),
            mean_charge=("energy_delivered_kwh", "mean"),
            mean_charges=("n_charges", "mean"),
            mean_dist=("total_distance_m", "mean"),
            mean_ms=("mean_decision_runtime_ms", "mean"),
            sum_reserve=("battery_reserve_violations", "sum"),
            sum_exhaust=("battery_exhaustion", "sum"),
            sum_strand=("n_strandings", "sum"),
        )
        .sort_values(["delay_s", "treatment"])
    )
    summary.to_csv(OUT / "final_locked_summary.csv", index=False)

    paired = []
    for delay in (0.0, 30.0, 120.0):
        for left, right in [
            ("H_CSC_LITE", "B_FULL_COMM"),
            ("H_CSC_LITE", "A_NONE_NOW"),
            ("H_CSC_LITE", "I_MATCHED_WAIT_ZERO_COMM"),
            ("H_CSC_LITE", "G_SELECTIVE_VALID_PEER"),
            ("H_CSC_LITE", "E_EVENT_TRIGGERED"),
            ("H_CSC_LITE", "J_MATCHED_WAIT_MESSAGE_PLACEBO"),
            ("H_CSC_LITE", "F_SELECTIVE_LEGACY"),
            ("H_CSC_LITE", "C_PERIODIC_COMM"),
            ("H_CSC_LITE", "D_RANDOM_BYTE_MATCHED"),
            ("J_MATCHED_WAIT_MESSAGE_PLACEBO", "I_MATCHED_WAIT_ZERO_COMM"),
        ]:
            if delay > 0 and left == "H_CSC_LITE" and right in {"E_EVENT_TRIGGERED", "C_PERIODIC_COMM", "D_RANDOM_BYTE_MATCHED"}:
                continue
            if left in set(ok.treatment) and right in set(ok.treatment):
                if delay > 0 and right not in DELAY_TREATMENTS and right != "H_CSC_LITE":
                    continue
                paired.append(paired_stats(ok, left, right, delay))
    (OUT / "final_locked_paired.json").write_text(json.dumps(paired, indent=2), encoding="utf-8")

    # Figure 3: Pareto @0
    sub = summary[summary.delay_s == 0.0]
    fig, ax = plt.subplots(figsize=(7.5, 5))
    ax.scatter(sub.mean_attempted_bytes, sub.mean_ot * 100)
    for _, r in sub.iterrows():
        ax.annotate(str(r.treatment).replace("_", "\n"), (r.mean_attempted_bytes, r.mean_ot * 100), fontsize=7)
    ax.set_xlabel("Mean attempted recipient bid bytes")
    ax.set_ylabel("Mean on-time rate (%)")
    ax.set_title("Locked-final: service vs communication (delay=0)")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(FIG / "fig3_pareto_delay0.png", dpi=160)
    plt.close(fig)

    # Figure 4: OT vs delay
    fig, ax = plt.subplots(figsize=(7.5, 5))
    for t in DELAY_TREATMENTS:
        s = summary[summary.treatment == t].sort_values("delay_s")
        if s.empty:
            continue
        ax.plot(s.delay_s, s.mean_ot * 100, marker="o", label=t)
    ax.set_xlabel("Message delay (s)")
    ax.set_ylabel("Mean on-time rate (%)")
    ax.set_title("Locked-final: service vs delay")
    ax.legend(fontsize=7)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(FIG / "fig4_service_vs_delay.png", dpi=160)
    plt.close(fig)

    # Figure 5: paired forest for primary contrasts @0 and @30
    primary = [p for p in paired if p.get("n", 0) >= 2 and p["left"] == "H_CSC_LITE" and p["right"] in {
        "B_FULL_COMM", "A_NONE_NOW", "I_MATCHED_WAIT_ZERO_COMM", "G_SELECTIVE_VALID_PEER", "E_EVENT_TRIGGERED"
    } and p["delay_s"] in (0.0, 30.0)]
    if primary:
        fig, ax = plt.subplots(figsize=(8, 5))
        y = np.arange(len(primary))
        means = [p["mean_delta_ot_pp"] for p in primary]
        los = [p["ci95_lo_pp"] for p in primary]
        his = [p["ci95_hi_pp"] for p in primary]
        labels = [f"{p['right']} @ {int(p['delay_s'])}s" for p in primary]
        ax.errorbar(means, y, xerr=[np.array(means) - np.array(los), np.array(his) - np.array(means)], fmt="o")
        ax.axvline(0, color="k", lw=0.8)
        ax.set_yticks(y)
        ax.set_yticklabels(labels, fontsize=8)
        ax.set_xlabel("Paired ΔOT (pp), H − comparator")
        ax.set_title("Locked-final primary paired differences")
        fig.tight_layout()
        fig.savefig(FIG / "fig5_paired_deltas.png", dpi=160)
        plt.close(fig)

    # Figure 6: energy
    fig, ax = plt.subplots(figsize=(7, 4.5))
    s0 = summary[summary.delay_s == 0.0].sort_values("treatment")
    ax.bar(range(len(s0)), s0.mean_energy)
    ax.set_xticks(range(len(s0)))
    ax.set_xticklabels(s0.treatment, rotation=75, ha="right", fontsize=7)
    ax.set_ylabel("Mean energy consumed (kWh)")
    ax.set_title("Locked-final energy (delay=0)")
    fig.tight_layout()
    fig.savefig(FIG / "fig6_energy_delay0.png", dpi=160)
    plt.close(fig)


def write_manifest(*, matched_bytes: float, n_jobs: int, repo_sha: str, cal: dict, hashes: dict) -> None:
    manifest = {
        "name": "final_locked_manifest",
        "implementation_sha": SOURCE_IMPL_SHA,
        "repository_sha_at_manifest": repo_sha,
        "csc_lite": CSC_LITE,
        "periodic_broadcast_s": PERIODIC_S,
        "periodic_state_broadcast": False,
        "random_matched_budget_attempted_bytes": matched_bytes,
        "random_calibration": cal,
        "primary_delays_s": [0, 30, 120],
        "zero_delay_treatments": ZERO_DELAY,
        "delay_treatments": DELAY_TREATMENTS,
        "n_vehicles": 3,
        "initial_soc": 0.35,
        "packet_loss_p_primary": 0.0,
        "expected_jobs": n_jobs,
        "expected_breakdown": {"delay0": 300, "delay30": 210, "delay120": 210},
        "primary_metric": "on_time_rate_all",
        "communication_primary_cost": "n_bid_attempted_bytes",
        "bootstrap_reps": 2000,
        "bootstrap_seed": 0,
        "noninferiority_margin_ot_absolute": 0.02,
        "noninferiority_margin_history": "Recorded in closeout/dev before Prompt 2; exploratory exposure to development data disclosed.",
        "no_retuning_after_locked_outcomes": True,
        "locked_final_path": "data/casablanca/evaluation_v1/locked_final",
        "content_hashes": hashes,
        "primary_comparisons": [
            "H vs B @0 (service + bytes + noninferiority)",
            "H vs A @0",
            "H vs I @30",
            "H vs G @30",
            "H vs I @120",
            "H vs E @0",
        ],
    }
    path = ROOT / "configs" / "final_locked_manifest.json"
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Wrote {path}", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--phase", choices=["all", "preflight", "locked", "analyze"], default="all")
    parser.add_argument("--skip-freeze-check", action="store_true")
    args = parser.parse_args()

    from race_casablanca.paths import project_root, scenarios_dir

    OUT.mkdir(parents=True, exist_ok=True)
    PREFLIGHT.mkdir(parents=True, exist_ok=True)
    FIG.mkdir(parents=True, exist_ok=True)

    locked_dir = project_root() / "data" / "casablanca" / "evaluation_v1" / "locked_final"
    assert locked_dir.exists(), "locked_final missing"
    locked_paths = sorted([p for p in locked_dir.iterdir() if p.is_dir()])
    assert len(locked_paths) == 30, f"expected 30 locked scenarios, got {len(locked_paths)}"

    # Content hashes (method + key sim sources)
    hash_files = [
        ROOT / "src/race_casablanca/policies/race_cooperative.py",
        ROOT / "src/race_casablanca/coordination/race_csc.py",
        ROOT / "src/race_casablanca/coordination/selective_protocol.py",
        ROOT / "src/race_casablanca/sim/environment.py",
        ROOT / "configs/final_frozen.json",
    ]
    hashes = {str(p.relative_to(ROOT)).replace("\\", "/"): file_sha256(p) for p in hash_files if p.exists()}

    import subprocess

    repo_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=str(ROOT), text=True).strip()

    train_paths = [p for p in sorted((scenarios_dir() / "train").iterdir()) if p.is_dir()][:8]
    cal = {"csc_lite_mean_attempted_bytes": 55793.0}
    if args.phase in ("all", "preflight"):
        print("=== PREFLIGHT CALIBRATION (train only) ===", flush=True)
        cal = calibrate(train_paths)
        if not args.skip_freeze_check:
            prompt2 = ROOT / "data/casablanca/online_results/prompt2/race_prompt2_primary.csv"
            # Use a few default-dev scenarios that appear in prompt2
            dev = project_root() / "data/casablanca/evaluation_v1/default"
            sample = sorted([p for p in dev.iterdir() if p.is_dir()])[:6]
            freeze_check(sample, prompt2)

    matched = float(cal.get("csc_lite_mean_attempted_bytes") or cal.get("random_matched_budget") or 55793.0)
    if (PREFLIGHT / "calibration_summary.json").exists():
        cal = json.loads((PREFLIGHT / "calibration_summary.json").read_text(encoding="utf-8"))
        matched = float(cal["random_matched_budget"])

    jobs = build_locked_jobs(locked_paths, matched, repo_sha)
    assert len(jobs) == 720, f"expected 720 jobs, got {len(jobs)}"

    # Manifest BEFORE locked outcomes analysis — write before running locked if preflight/all
    if args.phase in ("all", "preflight", "locked"):
        write_manifest(matched_bytes=matched, n_jobs=720, repo_sha=repo_sha, cal=cal, hashes=hashes)
        # Locked dataset checksums after freeze (provenance only; no outcome inspection yet)
        ds_hashes = {}
        for p in locked_paths:
            for f in sorted(p.rglob("*")):
                if f.is_file() and f.suffix in {".csv", ".json", ".geojson", ".txt"}:
                    rel = str(f.relative_to(locked_dir)).replace("\\", "/")
                    ds_hashes[rel] = file_sha256(f)
        (OUT / "locked_final_dataset_checksums.json").write_text(json.dumps(ds_hashes, indent=2), encoding="utf-8")

    csv_path = OUT / "final_locked_raw.csv"
    if args.phase in ("all", "locked"):
        print("=== LOCKED FINAL 720 RUNS ===", flush=True)
        run_jobs(jobs, csv_path, workers=args.workers, label="locked")

    if args.phase in ("all", "analyze") and csv_path.exists():
        analyze(csv_path)
        # Completeness check
        df = pd.read_csv(csv_path)
        n_ok = int(df.ok.astype(str).isin(["True", "true", "1"]).sum()) if "ok" in df.columns else 0
        n_keys = df.run_key.nunique() if "run_key" in df.columns else 0
        print(f"Locked rows={len(df)} unique_keys={n_keys} ok={n_ok}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
