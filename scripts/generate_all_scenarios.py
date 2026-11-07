"""Generate the fixed train/validation/test scenario splits from demand_default.yaml."""

from __future__ import annotations

import shutil
import subprocess
import sys

import yaml

from race_casablanca.paths import config_dir, project_root, scenarios_dir


def main() -> int:
    config = yaml.safe_load((config_dir() / "demand_default.yaml").read_text(encoding="utf-8"))
    splits = config["splits"]
    regimes = list(config["regimes"].keys())
    plan = [
        ("train", splits["train_seeds"]),
        ("validation", splits["validation_seeds"]),
        ("test", splits["test_seeds"]),
    ]
    py = sys.executable
    script = project_root() / "scripts" / "generate_scenarios.py"
    failures = []
    for split, seeds in plan:
        for seed in seeds:
            # Rotate regimes across seeds so each split covers all regimes.
            # Prefer stable ordering from YAML insertion order.
            regime = regimes[(abs(seed) - 1) % len(regimes)]
            cmd = [py, str(script), "--regime", regime, "--seed", str(seed), "--split", split]
            print(" ".join(cmd))
            result = subprocess.run(cmd, cwd=project_root())
            if result.returncode != 0:
                failures.append({"split": split, "seed": seed, "regime": regime, "code": result.returncode})

    # Remove legacy/extra scenarios excluded from the active release.
    for seed in splits.get("exclude_legacy_seeds", []):
        for split_dir in (scenarios_dir() / "train", scenarios_dir() / "validation", scenarios_dir() / "test"):
            if not split_dir.exists():
                continue
            for path in split_dir.glob(f"*_seed{seed}"):
                print(f"Removing legacy scenario from release: {path}")
                shutil.rmtree(path, ignore_errors=True)

    if failures:
        print({"failures": failures})
        return 1
    print({"status": "ok", "n_scenarios": sum(len(s) for _, s in plan)})
    return 0


if __name__ == "__main__":
    sys.exit(main())
