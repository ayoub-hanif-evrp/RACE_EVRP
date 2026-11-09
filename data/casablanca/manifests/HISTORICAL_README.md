# Historical / non-authoritative artifacts

The following files under `data/casablanca/manifests/` (and related reports) may disagree with the active `casablanca_release_v1` split and certification rules. They are retained for audit trail only.

| Artifact | Status |
| --- | --- |
| `constraint_binding_diagnosis.json` | **HISTORICAL** — legacy seed-42 / seed-4 narrative; not the active release authority |
| `reports/CONSTRAINT_BINDING_DIAGNOSIS.md` | **HISTORICAL** companion write-up |

**Active authority:** `casablanca_dataset_manifest.json` + per-scenario `scenario_metadata.json` under `scenarios/{train,validation,test}/`.

Stage 6 evaluation ensembles live under `data/casablanca/evaluation_v1/` and are synthetic expansions, not replacements of the release.
