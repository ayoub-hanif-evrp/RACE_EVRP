"""Integrity of the downloaded Jilin partition."""

from __future__ import annotations

import json

import numpy as np
import pyarrow.parquet as pq

from lade_audit.constants import (
    CARD_DECLARED_ROWS,
    EXPECTED_PARQUET_BYTES,
    EXPECTED_PARQUET_SHA256,
    REQUIRED_COLUMNS,
    REVISION,
)
from lade_audit.hashing import sha256_file
from lade_audit.paths import manifest_path, raw_parquet_path


def test_published_file_matches_lfs_oid_and_schema() -> None:
    path = raw_parquet_path()
    assert path.is_file(), "Download the Jilin parquet before running integrity tests."
    assert path.stat().st_size == EXPECTED_PARQUET_BYTES
    assert sha256_file(path) == EXPECTED_PARQUET_SHA256

    manifest = json.loads(manifest_path().read_text(encoding="utf-8"))
    assert manifest["revision"] == REVISION
    record = next(item for item in manifest["files"] if item["role"] == "jilin_pickup_partition")
    assert record["checksum_matches_published_lfs_oid"] is True
    assert record["sha256"] == EXPECTED_PARQUET_SHA256

    parquet = pq.ParquetFile(path)
    assert parquet.metadata.num_rows == CARD_DECLARED_ROWS
    assert tuple(field.name for field in parquet.schema_arrow) == REQUIRED_COLUMNS
    cities = pq.read_table(path, columns=["city"]).column("city").unique().to_pylist()
    assert cities == ["Jilin"]
    order_ids = pq.read_table(path, columns=["order_id"]).column("order_id").to_numpy()
    assert len(np.unique(order_ids)) == len(order_ids)
