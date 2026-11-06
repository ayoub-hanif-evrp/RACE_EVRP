"""Pinned identity of the LaDe-P Jilin file audited in this project.

The checksum and size are the Git-LFS object identifier and byte size reported
by the Hugging Face dataset API for revision ``REVISION``. They are checks
against the published object, not values computed from a local substitute.
"""

from __future__ import annotations

REPO_ID = "Cainiao-AI/LaDe-P"
REPO_TYPE = "dataset"
REVISION = "f1ddd8dd163028dd5a8ab7d7c83b198ebd2f2167"
PARQUET_REPO_PATH = "data/pickup_jl-00000-of-00001-9b430a56a935f284.parquet"
RAW_PARQUET_NAME = "pickup_jl-00000-of-00001-9b430a56a935f284.parquet"
README_REPO_PATH = "README.md"
RAW_README_NAME = "LaDe-P_README.md"

# Git-LFS oid for PARQUET_REPO_PATH at REVISION, queried from the dataset API.
EXPECTED_PARQUET_SHA256 = "043bdc91ff0c5906ac810e6097407226bc2c51da68bda6f40727f57aaf2737f9"
EXPECTED_PARQUET_BYTES = 20_772_658

# Row count declared in the dataset card for the pickup_jl split.
CARD_DECLARED_ROWS = 261_801

SOURCE_PAGE = "https://huggingface.co/datasets/Cainiao-AI/LaDe-P"
PARQUET_URL = (
    "https://huggingface.co/datasets/Cainiao-AI/LaDe-P/resolve/"
    f"{REVISION}/{PARQUET_REPO_PATH}"
)
README_URL = (
    "https://huggingface.co/datasets/Cainiao-AI/LaDe-P/resolve/"
    f"{REVISION}/{README_REPO_PATH}"
)

# Placeholder used only to order month-day timestamps. It is not a year
# observed in the file. 2001 is not a leap year; May-October does not depend
# on that fact, and any December-to-January wrap is flagged separately.
ORDERING_YEAR = 2001

REQUIRED_COLUMNS = (
    "order_id",
    "region_id",
    "city",
    "courier_id",
    "accept_time",
    "time_window_start",
    "time_window_end",
    "lng",
    "lat",
    "aoi_id",
    "aoi_type",
    "pickup_time",
    "pickup_gps_time",
    "pickup_gps_lng",
    "pickup_gps_lat",
    "accept_gps_time",
    "accept_gps_lng",
    "accept_gps_lat",
    "ds",
)

PAPER_CITATION = {
    "authors": (
        "Lixia Wu, Haomin Wen, Haoyuan Hu, Xiaowei Mao, Yutong Xia, "
        "Ergang Shan, Jianbin Zheng, Junhong Lou, Yuxuan Liang, "
        "Liuqing Yang, Roger Zimmermann, Youfang Lin, and Huaiyu Wan"
    ),
    "title": "LaDe: The First Comprehensive Last-mile Express Dataset from Industry",
    "venue": "Proceedings of the 30th ACM SIGKDD Conference on Knowledge Discovery and Data Mining",
    "year": 2024,
    "pages": "5991-6002",
    "doi": "10.1145/3637528.3671548",
    "arxiv": "2306.10675",
    "note": (
        "The KDD 2024 proceedings title uses 'Express'. The arXiv preprint "
        "title uses 'Delivery'. The dataset card citation block is a placeholder."
    ),
}
