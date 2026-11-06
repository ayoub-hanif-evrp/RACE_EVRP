"""Join HCP RGPH-2024 commune/arrondissement population to workbook zones."""

from __future__ import annotations

import re
import sys
import unicodedata

import pandas as pd

from race_casablanca.io_utils import utc_now, write_json
from race_casablanca.paths import manifest_dir, raw_dir, traffic_dir, zones_dir


def _norm(name: str) -> str:
    text = unicodedata.normalize("NFKD", str(name))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower().replace("-", " ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


# Map workbook names to HCP French labels observed in RGPH-2024 Excel.
HCP_ALIASES = {
    "echchallalate": ["commune d ech challalate", "ech challalate"],
    "sidi maarouf": ["sidi maarouf"],
    "anfa": ["arrondissement d anfa", "anfa"],
    "assoukhour assawda": ["arrondissement d asoukhour assawda", "asoukhour assawda", "sbata"],
    "ben msick": ["arrondissement de ben m sick", "ben m sick", "ben msick"],
    "bou chentouf": ["bou chentouf", "bouchentouf"],
    "el maarif": ["arrondissement de ma arif", "ma arif", "maarif"],
    "hay hassani": ["arrondissement de hay hassani", "hay hassani"],
    "hay mohammadi": ["arrondissement de hay mohammadi", "hay mohammadi"],
    "ain chock": ["arrondissement d ain chock", "ain chock"],
    "ain sebaa": ["arrondissement d ain sebaa", "ain sebaa"],
    "al fida": ["arrondissement d al fida", "al fida"],
    "al idrissia": ["al idrissia", "idrissia"],
    "lissasfa": ["lissasfa"],
    "mers sultan": ["arrondissement de mers sultan", "mers sultan"],
    "moulay rachid": ["arrondissement de moulay rachid", "moulay rachid"],
    "sidi belyout": ["arrondissement de sidi belyout", "sidi belyout"],
    "sidi moumen": ["arrondissement de sidi moumen", "sidi moumen"],
    "sidi othmane": ["arrondissement de sidi othmane", "sidi othmane", "sidi othman"],
    "ahl laghlam": ["ahl laghlam", "ahl loghlam"],
    "sidi bernoussi": ["arrondissement de sidi bernoussi", "sidi bernoussi"],
    "moulay youssef": ["moulay youssef"],
}


def _load_hcp_units(path) -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name=0, header=None)
    # Fixed layout from HCP legal-population Excel:
    # col0 French name, col1 Marocains, col2 Etrangers, col3 Population, col4 Menages
    rows = []
    for i in range(7, len(df)):
        name = df.iloc[i, 0]
        pop = df.iloc[i, 3]
        hh = df.iloc[i, 4]
        if pd.isna(name) or pd.isna(pop):
            continue
        name_s = str(name).strip()
        if not re.match(r"^(Arrondissement|Commune|Préfecture|Province|Région)\b", name_s, re.I):
            # Keep only territorial units; skip "dont le centre..." notes.
            if not re.match(r"^(Arrondissement|Commune)\b", name_s, re.I):
                continue
        try:
            population = float(pop)
            households = float(hh) if pd.notna(hh) else None
        except (TypeError, ValueError):
            continue
        rows.append(
            {
                "hcp_name": name_s,
                "population": population,
                "households_hcp": households,
                "name_norm": _norm(name_s),
                "row_index": i,
            }
        )
    return pd.DataFrame(rows)


def main() -> int:
    path = raw_dir() / "hcp" / "rgph2024_population_legale.xlsx"
    if not path.exists():
        raise SystemExit(f"Missing HCP workbook at {path}")
    hcp = _load_hcp_units(path)
    # Prefer arrondissement/commune rows for matching.
    hcp_pref = hcp[hcp["hcp_name"].str.match(r"^(Arrondissement|Commune)\b", case=False, na=False)].copy()
    communes = pd.read_csv(traffic_dir() / "communes.csv")
    # Preserve original workbook household/density covariates if present.
    workbook_hh = communes["households"] if "households" in communes.columns else None
    workbook_density = communes["density"] if "density" in communes.columns else None

    rows = []
    for _, commune in communes.iterrows():
        key = _norm(commune["commune"])
        aliases = [_norm(a) for a in HCP_ALIASES.get(key, [key])]
        aliases.append(key)
        hit = hcp_pref[hcp_pref["name_norm"].isin(aliases)]
        if hit.empty:
            hit = hcp_pref[
                hcp_pref["name_norm"].apply(lambda n: any(a in n or n in a for a in aliases if len(a) > 3))
            ]
        if hit.empty:
            rows.append(
                {
                    "commune": commune["commune"],
                    "zip_code": commune["zip_code"],
                    "population": None,
                    "hcp_name": None,
                    "matched": False,
                }
            )
            continue
        # Prefer exact-ish arrondissement matches (shortest name among ties).
        chosen = hit.assign(_len=hit["hcp_name"].str.len()).sort_values("_len").iloc[0]
        rows.append(
            {
                "commune": commune["commune"],
                "zip_code": commune["zip_code"],
                "population": float(chosen["population"]),
                "hcp_name": chosen["hcp_name"],
                "matched": True,
            }
        )
    out = pd.DataFrame(rows)
    base = communes[["commune", "zip_code"]].copy()
    if workbook_hh is not None:
        base["households"] = workbook_hh
    if workbook_density is not None:
        base["density"] = workbook_density
    merged = base.merge(out[["commune", "zip_code", "population", "hcp_name"]], on=["commune", "zip_code"], how="left")
    unmatched_mask = merged["population"].isna()
    if unmatched_mask.any() and "households" in merged.columns:
        # Secondary covariate: scale unmatched zones by workbook households relative to matched median.
        matched_pop = merged.loc[~unmatched_mask, "population"]
        matched_hh = merged.loc[~unmatched_mask, "households"]
        if matched_hh.notna().any() and matched_pop.notna().any() and float(matched_hh.median()) > 0:
            ratio = float(matched_pop.median() / matched_hh.median())
            merged.loc[unmatched_mask, "population"] = merged.loc[unmatched_mask, "households"] * ratio
            pop_note = (
                "Unmatched communes received household-scaled synthetic population "
                f"(ratio={ratio:.4f} from matched median pop/households). Labeled modeled."
            )
        else:
            merged["population"] = merged["population"].fillna(1.0)
            pop_note = "Fallback population=1 for unmatched; check HCP join."
    elif unmatched_mask.any():
        merged["population"] = merged["population"].fillna(1.0)
        pop_note = "Fallback population=1 for unmatched; check HCP join."
    else:
        pop_note = "All workbook communes matched to HCP population rows."

    merged.to_csv(traffic_dir() / "communes.csv", index=False)
    zones_dir().mkdir(parents=True, exist_ok=True)
    out.to_csv(zones_dir() / "hcp_zone_population.csv", index=False)
    summary = {
        "generated_at_utc": utc_now(),
        "n_workbook": int(len(out)),
        "n_matched": int(out["matched"].sum()),
        "unmatched": out.loc[~out["matched"], "commune"].tolist(),
        "n_hcp_units_parsed": int(len(hcp)),
        "note": pop_note,
        "claim": (
            "HCP RGPH-2024 legal population joined to workbook commune names where matched. "
            "Unmatched zones use documented household-scaled placeholders, not claimed census counts."
        ),
    }
    write_json(manifest_dir() / "hcp_join_manifest.json", summary)
    print(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
