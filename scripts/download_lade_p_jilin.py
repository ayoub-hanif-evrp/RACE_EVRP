"""Download the published LaDe-P Jilin parquet and record its provenance.

The script copies the file byte for byte. It does not create a substitute
table if the download or checksum check fails.
"""

from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime, timezone

from huggingface_hub import hf_hub_download

from lade_audit.constants import (
    EXPECTED_PARQUET_BYTES,
    EXPECTED_PARQUET_SHA256,
    PAPER_CITATION,
    PARQUET_REPO_PATH,
    PARQUET_URL,
    RAW_PARQUET_NAME,
    RAW_README_NAME,
    README_REPO_PATH,
    README_URL,
    REPO_ID,
    REPO_TYPE,
    REVISION,
    SOURCE_PAGE,
)
from lade_audit.hashing import sha256_file
from lade_audit.paths import manifest_path, raw_dir


def _download(repo_path: str) -> str:
    return hf_hub_download(
        repo_id=REPO_ID,
        repo_type=REPO_TYPE,
        filename=repo_path,
        revision=REVISION,
    )


def main() -> int:
    destination_dir = raw_dir()
    destination_dir.mkdir(parents=True, exist_ok=True)
    manifest_path().parent.mkdir(parents=True, exist_ok=True)

    print(f"Repository: {REPO_ID}")
    print(f"Revision:   {REVISION}")
    print(f"File:       {PARQUET_REPO_PATH}")

    cached_parquet = _download(PARQUET_REPO_PATH)
    cached_readme = _download(README_REPO_PATH)

    parquet_dest = destination_dir / RAW_PARQUET_NAME
    readme_dest = destination_dir / RAW_README_NAME
    shutil.copyfile(cached_parquet, parquet_dest)
    shutil.copyfile(cached_readme, readme_dest)

    parquet_sha = sha256_file(parquet_dest)
    readme_sha = sha256_file(readme_dest)
    parquet_size = parquet_dest.stat().st_size
    verified = parquet_sha == EXPECTED_PARQUET_SHA256 and parquet_size == EXPECTED_PARQUET_BYTES

    manifest = {
        "retrieved_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "repo_id": REPO_ID,
        "repo_type": REPO_TYPE,
        "revision": REVISION,
        "source_page": SOURCE_PAGE,
        "license_recorded_on_huggingface_card": "apache-2.0",
        "license_stated_in_paper": "CC BY-NC 4.0",
        "license_note": (
            "The Hugging Face dataset card tags this repository as apache-2.0. "
            "The LaDe paper and its datasheet state CC BY-NC 4.0 and request citation. "
            "Both statements are recorded; this project does not resolve the conflict."
        ),
        "citation": PAPER_CITATION,
        "files": [
            {
                "role": "jilin_pickup_partition",
                "repo_path": PARQUET_REPO_PATH,
                "local_path": str(parquet_dest.relative_to(destination_dir.parent.parent)),
                "source_url": PARQUET_URL,
                "bytes": parquet_size,
                "sha256": parquet_sha,
                "expected_sha256": EXPECTED_PARQUET_SHA256,
                "expected_bytes": EXPECTED_PARQUET_BYTES,
                "checksum_matches_published_lfs_oid": verified,
            },
            {
                "role": "dataset_card_snapshot",
                "repo_path": README_REPO_PATH,
                "local_path": str(readme_dest.relative_to(destination_dir.parent.parent)),
                "source_url": README_URL,
                "bytes": readme_dest.stat().st_size,
                "sha256": readme_sha,
            },
        ],
    }
    manifest_path().write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Wrote {parquet_dest}")
    print(f"SHA-256 {parquet_sha}")
    print(f"Bytes   {parquet_size}")
    print(f"Verified against published LFS oid: {verified}")
    print(f"Manifest {manifest_path()}")
    if not verified:
        print("Checksum or size does not match the published object. No analysis should treat this file as verified.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
