#!/usr/bin/env python
"""Stage 4B: exact/enumerative tiny charge–commitment instances A–D."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from race_casablanca.exact.charge_commit_enum import results_to_rows, run_all_canned
from race_casablanca.paths import project_root


def main() -> int:
    results = run_all_canned()
    rows = results_to_rows(results)
    out_dir = project_root() / "data" / "casablanca" / "online_results"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_json = out_dir / "stage4b_exact_toys.json"
    out_json.write_text(json.dumps(rows, indent=2), encoding="utf-8")

    print("Stage 4B exact toys", flush=True)
    for r in rows:
        print(
            f"  {r['instance']}: best_ot={r['best_on_time']} "
            f"greedy={r['greedy_on_time']} always_full={r['always_full_on_time']} "
            f"enum={r['n_enumerated']}",
            flush=True,
        )
    print(f"Wrote {out_json}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
