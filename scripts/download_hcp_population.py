"""Download the official HCP RGPH-2024 legal population Excel workbook.

Tries documented HCP pages and records failure without fabricating tables.
"""

from __future__ import annotations

import re
import sys
from urllib.parse import urljoin

import requests

from race_casablanca.hashing import sha256_file
from race_casablanca.io_utils import download_file, utc_now, write_json
from race_casablanca.paths import manifest_dir, raw_dir

PAGES = [
    "https://www.hcp.ma/downloads/RGPH-2024_t22752.html",
    "https://www.hcp.ma/reg-casablanca/%D9%86%D8%AA%D8%A7%D8%A6%D8%AC-%D8%A7%D9%84%D8%A5%D8%AD%D8%B5%D8%A7%D8%A1-%D8%A7%D9%84%D8%B9%D8%A7%D9%85-%D9%84%D9%84%D8%B3%D9%83%D8%A7%D9%86-%D9%88%D8%A7%D9%84%D8%B3%D9%83%D9%86%D9%89-2024_a126.html",
    "https://www.hcp.ma/Population-legale-du-Royaume-du-Maroc-repartie-par-regions-provinces-et-prefectures-et-communes-selon-les-resultats-du_a3975.html",
]

# Known direct attachment pattern observed on HCP regional pages for the Excel release.
CANDIDATE_DIRECT = [
    "https://www.hcp.ma/file/242341/",  # Population legale RGPH 2024, format EXCEL
]


def _discover_excel_urls(html: str, base: str) -> list[str]:
    hrefs = re.findall(r'href=["\']([^"\']+)["\']', html, flags=re.IGNORECASE)
    found = []
    for href in hrefs:
        lower = href.lower()
        if lower.endswith(".xlsx") or ("excel" in lower and "rgph" in lower):
            found.append(urljoin(base, href))
        if "file/" in lower and "xlsx" in html[max(0, html.lower().find(href) - 200) : html.lower().find(href) + 200]:
            found.append(urljoin(base, href))
    # Also catch explicit Excel filenames in visible text links.
    for match in re.finditer(r'(https?://[^\s"\']+\.xlsx)', html, flags=re.IGNORECASE):
        found.append(match.group(1))
    for match in re.finditer(r'href=["\']([^"\']*Population[^"\']*EXCEL[^"\']*)["\']', html, flags=re.IGNORECASE):
        found.append(urljoin(base, match.group(1)))
    # Deduplicate preserving order.
    seen = set()
    ordered = []
    for url in found:
        if url not in seen:
            seen.add(url)
            ordered.append(url)
    return ordered


def main() -> int:
    session = requests.Session()
    session.headers.update({"User-Agent": "RACE-EVRP-research/0.1 (academic dataset acquisition)"})
    discovered: list[str] = []
    page_errors: list[dict] = []
    for page in PAGES:
        try:
            response = session.get(page, timeout=60)
            response.raise_for_status()
            discovered.extend(_discover_excel_urls(response.text, page))
        except Exception as exc:  # noqa: BLE001
            page_errors.append({"page": page, "error": str(exc)})

    candidates = discovered + CANDIDATE_DIRECT
    if not candidates:
        raise RuntimeError(
            "No HCP Excel download URL could be discovered from the documented pages. "
            f"Page errors: {page_errors}"
        )

    destination = raw_dir() / "hcp" / "rgph2024_population_legale.xlsx"
    last_error = None
    used_url = None
    for url in candidates:
        try:
            print(f"Trying {url}")
            download_file(url, destination, timeout=180)
            # Basic sanity: Excel ZIP/OLE signature.
            header = destination.read_bytes()[:8]
            if header[:2] != b"PK" and header[:8] != b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
                raise RuntimeError(f"Downloaded bytes do not look like an Excel file from {url}")
            used_url = url
            break
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if destination.exists():
                destination.unlink()
    if used_url is None:
        raise RuntimeError(f"All HCP Excel download attempts failed. Last error: {last_error}")

    digest = sha256_file(destination)
    manifest = {
        "retrieved_at_utc": utc_now(),
        "source": "Haut-Commissariat au Plan (HCP)",
        "product": "RGPH 2024 legal population",
        "pages_checked": PAGES,
        "download_url": used_url,
        "discovered_candidates": candidates,
        "page_errors": page_errors,
        "filename": destination.name,
        "bytes": destination.stat().st_size,
        "sha256": digest,
        "attribution": "Haut-Commissariat au Plan, Royaume du Maroc, RGPH 2024",
    }
    write_json(manifest_dir() / "hcp_population_manifest.json", manifest)
    print(f"Wrote {destination}")
    print(f"SHA-256 {digest}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"DOWNLOAD FAILED: {exc}", file=sys.stderr)
        write_json(
            manifest_dir() / "hcp_population_manifest.json",
            {"retrieved_at_utc": utc_now(), "status": "failed", "error": str(exc), "pages": PAGES},
        )
        sys.exit(1)
