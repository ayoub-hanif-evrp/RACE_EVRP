"""Download the published Casablanca traffic workbook from Mendeley Data.

DOI: 10.17632/8hj76bpzpv.1
Does not fabricate a substitute workbook if the download fails.
"""

from __future__ import annotations

import sys

import requests

from race_casablanca.hashing import sha256_file
from race_casablanca.io_utils import download_file, utc_now, write_json
from race_casablanca.paths import manifest_dir, project_root, raw_dir

DATASET_ID = "8hj76bpzpv"
VERSION = "1"
DOI = "10.17632/8hj76bpzpv.1"
PAGE = "https://data.mendeley.com/datasets/8hj76bpzpv/1"
DATASET_API = f"https://data.mendeley.com/public-api/datasets/{DATASET_ID}"
EXPECTED_SHA256 = "4778abffbe3d7791afa58069fc8a98b6e89995174d4c64401d9367221c42d17d"
EXPECTED_BYTES = 1_720_067


def main() -> int:
    print(f"Querying Mendeley dataset API: {DATASET_API}")
    response = requests.get(DATASET_API, timeout=60)
    response.raise_for_status()
    payload = response.json()
    files = payload.get("files") or []
    excel = [
        item
        for item in files
        if str(item.get("filename", "")).lower().endswith((".xlsx", ".xls"))
    ]
    if not excel:
        raise RuntimeError(f"No Excel workbook listed for {DOI}")
    chosen = excel[0]
    filename = chosen["filename"]
    content_url = chosen.get("content_details", {}).get("download_url")
    if not content_url:
        raise RuntimeError(f"No download URL available for {filename}")

    destination = raw_dir() / "traffic" / filename
    print(f"Downloading {filename}")
    print(f"URL: {content_url}")
    download_file(content_url, destination, timeout=180)
    digest = sha256_file(destination)
    size = destination.stat().st_size
    verified = digest == EXPECTED_SHA256 and size == EXPECTED_BYTES
    manifest = {
        "retrieved_at_utc": utc_now(),
        "source": "Mendeley Data",
        "doi": DOI,
        "version": VERSION,
        "page": PAGE,
        "dataset_api": DATASET_API,
        "download_url": content_url,
        "filename": filename,
        "local_path": str(destination.relative_to(project_root())),
        "bytes": size,
        "sha256": digest,
        "expected_sha256": EXPECTED_SHA256,
        "expected_bytes": EXPECTED_BYTES,
        "checksum_matches_published": verified,
        "license": "CC BY 4.0",
        "citation": (
            "Rouky, N., & Bousouf, A. (2023). Dataset for traffic analysis in "
            "Casablanca, Morocco (Version 1) [Data set]. Mendeley Data. "
            "https://doi.org/10.17632/8hj76bpzpv.1"
        ),
        "api_file_record": chosen,
    }
    write_json(manifest_dir() / "traffic_workbook_manifest.json", manifest)
    print(f"Wrote {destination}")
    print(f"SHA-256 {digest}")
    print(f"Verified against published hash: {verified}")
    if not verified:
        print("Checksum or size does not match the published object.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"DOWNLOAD FAILED: {exc}", file=sys.stderr)
        write_json(
            manifest_dir() / "traffic_workbook_manifest.json",
            {
                "retrieved_at_utc": utc_now(),
                "status": "failed",
                "error": str(exc),
                "doi": DOI,
                "page": PAGE,
                "dataset_api": DATASET_API,
            },
        )
        sys.exit(1)
