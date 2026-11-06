"""Download the fixed Geofabrik Morocco OSM extract and verify its MD5."""

from __future__ import annotations

import sys

from race_casablanca.hashing import md5_file, sha256_file
from race_casablanca.io_utils import download_file, utc_now, write_json
from race_casablanca.paths import manifest_dir, raw_dir

PBF_NAME = "morocco-260101.osm.pbf"
MD5_NAME = "morocco-260101.osm.pbf.md5"
PBF_URL = f"https://download.geofabrik.de/africa/{PBF_NAME}"
MD5_URL = f"https://download.geofabrik.de/africa/{MD5_NAME}"
PAGE = "https://download.geofabrik.de/africa/morocco.html"


def main() -> int:
    osm_dir = raw_dir() / "osm"
    pbf_path = osm_dir / PBF_NAME
    md5_path = osm_dir / MD5_NAME
    print(f"Downloading {PBF_URL}")
    download_file(PBF_URL, pbf_path, timeout=600)
    print(f"Downloading {MD5_URL}")
    download_file(MD5_URL, md5_path, timeout=60)
    expected = md5_path.read_text(encoding="utf-8").strip().split()[0].lower()
    observed = md5_file(pbf_path)
    verified = observed == expected
    manifest = {
        "retrieved_at_utc": utc_now(),
        "source": "Geofabrik",
        "page": PAGE,
        "download_url": PBF_URL,
        "md5_url": MD5_URL,
        "filename": PBF_NAME,
        "bytes": pbf_path.stat().st_size,
        "md5": observed,
        "expected_md5": expected,
        "md5_verified": verified,
        "sha256": sha256_file(pbf_path),
        "license_note": "OpenStreetMap data is available under the ODbL.",
        "attribution": "© OpenStreetMap contributors",
    }
    write_json(manifest_dir() / "morocco_osm_manifest.json", manifest)
    print(f"Wrote {pbf_path}")
    print(f"MD5 verified: {verified}")
    if not verified:
        print("MD5 mismatch against Geofabrik checksum file.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"DOWNLOAD FAILED: {exc}", file=sys.stderr)
        write_json(
            manifest_dir() / "morocco_osm_manifest.json",
            {"retrieved_at_utc": utc_now(), "status": "failed", "error": str(exc), "url": PBF_URL},
        )
        sys.exit(1)
