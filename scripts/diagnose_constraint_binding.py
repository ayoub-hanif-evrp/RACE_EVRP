"""Diagnose energy/payload/window binding on existing certified baseline scenarios."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import yaml

from race_casablanca.io_utils import utc_now, write_json
from race_casablanca.paths import config_dir, manifest_dir, report_dir, scenarios_dir


def _analyze_schedule(schedule: pd.DataFrame, fleet: dict) -> dict:
    usable = float(fleet["usable_battery_kwh"])
    reserve = usable * float(fleet["min_reserve_soc"])
    payload_cap = float(fleet["payload_kg"])
    pickups = schedule[~schedule["request_id"].astype(str).str.startswith("RETURN-")].copy()
    batteries = []
    loads = []
    window_slacks = []
    for _, row in pickups.iterrows():
        if "battery_after_kwh" in pickups.columns and pd.notna(row.get("battery_after_kwh")):
            batteries.append(float(row["battery_after_kwh"]))
        if "load_after_kg" in pickups.columns and pd.notna(row.get("load_after_kg")):
            loads.append(float(row["load_after_kg"]))
        # Prefer end-of-service vs tw_end if present on schedule; else skip.
        if "tw_end_min" in pickups.columns and "planned_end_min" in pickups.columns:
            if pd.notna(row.get("tw_end_min")) and pd.notna(row.get("planned_end_min")):
                window_slacks.append(float(row["tw_end_min"]) - float(row["planned_end_min"]))
    return {
        "n_pickups": int(len(pickups)),
        "n_returns": int(schedule["request_id"].astype(str).str.startswith("RETURN-").sum()),
        "min_battery_after_kwh": float(min(batteries)) if batteries else None,
        "reserve_kwh": reserve,
        "battery_headroom_kwh": (float(min(batteries)) - reserve) if batteries else None,
        "max_load_kg": float(max(loads)) if loads else None,
        "payload_cap_kg": payload_cap,
        "payload_headroom_kg": (payload_cap - float(max(loads))) if loads else None,
        "min_window_slack_min": float(min(window_slacks)) if window_slacks else None,
        "median_window_slack_min": float(pd.Series(window_slacks).median()) if window_slacks else None,
    }


def main() -> int:
    fleet = yaml.safe_load((config_dir() / "fleet_default.yaml").read_text(encoding="utf-8"))
    roots = []
    for split in ["train", "validation", "test"]:
        d = scenarios_dir() / split
        if d.exists():
            roots.extend(sorted(p for p in d.iterdir() if p.is_dir() and "baseline" in p.name))

    rows = []
    for scenario_dir in roots:
        meta_path = scenario_dir / "scenario_metadata.json"
        if not meta_path.exists():
            continue
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        feas = meta.get("feasibility") or {}
        if not feas.get("certified_feasible"):
            continue
        witness = scenario_dir / "witnesses" / "reference_schedule.csv"
        if not witness.exists():
            continue
        schedule = pd.read_csv(witness)
        detail = _analyze_schedule(schedule, fleet)
        # Prefer certificate summary fields when present.
        detail.update(
            {
                "scenario": f"{scenario_dir.parent.name}/{scenario_dir.name}",
                "certified_feasible": True,
                "cert_min_battery_after_kwh": feas.get("min_battery_after_kwh"),
                "cert_total_travel_distance_m": feas.get("total_travel_distance_m"),
                "cert_vehicles_used": feas.get("vehicles_used"),
                "cert_share_within_window": feas.get("share_within_window"),
            }
        )
        # Vehicle-level battery from independent validator if available.
        vehicles = (feas.get("independent_validator") or {}).get("vehicles") or {}
        if vehicles:
            bat = [float(v.get("battery_kwh")) for v in vehicles.values() if v.get("battery_kwh") is not None]
            load = [float(v.get("load_kg")) for v in vehicles.values() if v.get("load_kg") is not None]
            if bat:
                detail["validator_min_battery_kwh"] = float(min(bat))
                detail["battery_headroom_kwh"] = float(min(bat)) - float(fleet["usable_battery_kwh"]) * float(
                    fleet["min_reserve_soc"]
                )
            if load:
                detail["validator_max_final_load_kg"] = float(max(load))
                detail["payload_headroom_kg"] = float(fleet["payload_kg"]) - float(max(load))
        rows.append(detail)

    frame = pd.DataFrame(rows)
    usable = float(fleet["usable_battery_kwh"])
    reserve = usable * float(fleet["min_reserve_soc"])
    summary = {
        "generated_at_utc": utc_now(),
        "fleet": {
            "usable_battery_kwh": usable,
            "min_reserve_soc": float(fleet["min_reserve_soc"]),
            "reserve_kwh": reserve,
            "payload_kg": float(fleet["payload_kg"]),
            "n_vehicles": int(fleet.get("n_vehicles", 0)),
        },
        "n_certified_baselines": int(len(frame)),
        "scenarios": rows,
        "aggregate": {
            "min_battery_headroom_kwh": float(frame["battery_headroom_kwh"].min())
            if not frame.empty and frame["battery_headroom_kwh"].notna().any()
            else None,
            "min_payload_headroom_kg": float(frame["payload_headroom_kg"].min())
            if not frame.empty and frame["payload_headroom_kg"].notna().any()
            else None,
            "energy_binds": False,
            "payload_binds": False,
            "windows_bind": None,
        },
        "scientific_note": (
            "Offline constructive witnesses with full request visibility. "
            "Comfortable residual battery/payload on baselines does not prove energy-risk "
            "coordination is a hard online problem; it only shows current baseline regimes "
            "are not energy- or payload-binding."
        ),
    }
    if summary["aggregate"]["min_battery_headroom_kwh"] is not None:
        summary["aggregate"]["energy_binds"] = summary["aggregate"]["min_battery_headroom_kwh"] < 1.0
    if summary["aggregate"]["min_payload_headroom_kg"] is not None:
        summary["aggregate"]["payload_binds"] = summary["aggregate"]["min_payload_headroom_kg"] < 10.0

    write_json(manifest_dir() / "constraint_binding_diagnosis.json", summary)
    md = report_dir() / "CONSTRAINT_BINDING_DIAGNOSIS.md"
    lines = [
        "# Constraint binding diagnosis (existing certified baselines)",
        "",
        f"Fleet usable battery {usable} kWh, reserve {reserve:.1f} kWh, payload {fleet['payload_kg']} kg.",
        "",
        f"Certified baselines analyzed: **{len(frame)}**.",
        "",
    ]
    if not frame.empty:
        lines.append("| Scenario | Min battery (kWh) | Headroom vs reserve | Max load (kg) | Payload headroom |")
        lines.append("| --- | ---: | ---: | ---: | ---: |")
        for row in rows:
            lines.append(
                f"| {row['scenario']} | "
                f"{row.get('validator_min_battery_kwh') or row.get('cert_min_battery_after_kwh')} | "
                f"{row.get('battery_headroom_kwh')} | "
                f"{row.get('validator_max_final_load_kg') or row.get('max_load_kg')} | "
                f"{row.get('payload_headroom_kg')} |"
            )
        lines.append("")
        lines.append(
            f"Energy binds (<1 kWh headroom): **{summary['aggregate']['energy_binds']}**. "
            f"Payload binds (<10 kg headroom): **{summary['aggregate']['payload_binds']}**."
        )
        lines.append("")
        lines.append(summary["scientific_note"])
    md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(summary["aggregate"], indent=2))
    print(f"Wrote {md}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
