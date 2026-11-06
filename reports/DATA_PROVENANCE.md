# Data provenance

This file records the exact object audited in Stage 1. The local parquet is a byte copy of the published file. No rows were added, removed, or rewritten.

## Source

| Item | Value |
| --- | --- |
| Repository | `Cainiao-AI/LaDe-P` |
| Repository type | Hugging Face dataset |
| Page | https://huggingface.co/datasets/Cainiao-AI/LaDe-P |
| Revision | `f1ddd8dd163028dd5a8ab7d7c83b198ebd2f2167` |
| Card `lastModified` reported by the dataset API | 2023-06-22T15:00:50Z |
| Split | `pickup_jl` |
| Repository path | `data/pickup_jl-00000-of-00001-9b430a56a935f284.parquet` |
| Resolve URL | https://huggingface.co/datasets/Cainiao-AI/LaDe-P/resolve/f1ddd8dd163028dd5a8ab7d7c83b198ebd2f2167/data/pickup_jl-00000-of-00001-9b430a56a935f284.parquet |
| Local copy | `data/raw/pickup_jl-00000-of-00001-9b430a56a935f284.parquet` |
| Bytes | 20,772,658 |
| SHA-256 | `043bdc91ff0c5906ac810e6097407226bc2c51da68bda6f40727f57aaf2737f9` |
| Check against the Git-LFS oid published for this revision | Match |
| Rows declared on the dataset card | 261,801 |
| Rows in the Parquet metadata | 261,801 |
| Retrieved | 2026-11-06T21:22:15Z |

The dataset-card snapshot saved with the same revision is `data/raw/LaDe-P_README.md` (8,065 bytes, SHA-256 `aba9162a3a494feb4fa90b5eb3931ad1803ea2785fe17ca3d9403c2014a92052`).

The machine-readable copy of this record is `data/manifests/lade_p_jilin_manifest.json`.

## What was downloaded

Only the Jilin pickup partition and the dataset card at the pinned revision. The other city files in `Cainiao-AI/LaDe-P` (Shanghai, Hangzhou, Chongqing, Yantai) were left on the server.

`Cainiao-AI/LaDe` is a separate Hugging Face dataset that distributes pickup tables as CSV and describes road-network and trajectory files. Those files were not downloaded. Nothing in this audit treats them as part of the observed Jilin table.

## License statements on record

Two official statements disagree.

- The Hugging Face dataset card for `Cainiao-AI/LaDe-P` is tagged `apache-2.0`.
- The LaDe paper and its datasheet state that the dataset is distributed under CC BY-NC 4.0 and ask users to cite the paper: https://creativecommons.org/licenses/by-nc/4.0/

This project records both statements and does not choose between them. Any later public redistribution needs an explicit license decision. Citation of the paper is required by the datasheet regardless of that choice.

## Citation

Wu, Lixia, Haomin Wen, Haoyuan Hu, Xiaowei Mao, Yutong Xia, Ergang Shan, Jianbin Zheng, Junhong Lou, Yuxuan Liang, Liuqing Yang, Roger Zimmermann, Youfang Lin, and Huaiyu Wan. 2024. "LaDe: The First Comprehensive Last-mile Express Dataset from Industry." In *Proceedings of the 30th ACM SIGKDD Conference on Knowledge Discovery and Data Mining*, 5991–6002. https://doi.org/10.1145/3637528.3671548

The arXiv preprint (2306.10675) uses the title "LaDe: The First Comprehensive Last-mile Delivery Dataset from Industry." The KDD 2024 title uses "Express." The citation block on the Hugging Face card is a placeholder (`{xxx}`), so the proceedings record above is the citation used here.

```bibtex
@inproceedings{wu2024lade,
  author = {Wu, Lixia and Wen, Haomin and Hu, Haoyuan and Mao, Xiaowei and Xia, Yutong and Shan, Ergang and Zheng, Jianbin and Lou, Junhong and Liang, Yuxuan and Yang, Liuqing and Zimmermann, Roger and Lin, Youfang and Wan, Huaiyu},
  title = {LaDe: The First Comprehensive Last-mile Express Dataset from Industry},
  booktitle = {Proceedings of the 30th ACM SIGKDD Conference on Knowledge Discovery and Data Mining},
  pages = {5991--6002},
  year = {2024},
  publisher = {Association for Computing Machinery},
  doi = {10.1145/3637528.3671548}
}
```

## Collection statements taken from the paper

These statements describe the publishers' collection process. They are not columns in the parquet file.

- Cainiao collected the logs. Couriers carried personal digital assistants that reported status, including GPS, to the platform.
- The paper says couriers pick up packages from sender customers and return to a depot. The Jilin table contains no depot coordinate and no return-to-depot timestamp.
- Cities were chosen for diversity. Within a city, the paper says 30 regions were randomly selected and couriers were then sampled inside those regions. The Jilin pickup file contains 15 distinct `region_id` values.
- Latitude and longitude were perturbed. The paper limits stated coordinate accuracy to about 10 meters.
- Courier and package identifiers were anonymized.
- The datasheet says the extract covers "May and November of a recent year." The `ds` codes in this file run from 1 May through 31 October and contain no year and no November code.
- The paper's Table 2 lists Jilin pickup as 6 months, a 20 km by 20 km spatial span, 665 couriers, 261k packages, and 13.8 packages per courier-day. The file matches the courier count, the package count, and the mean daily package count. The coordinates do not fit inside one 20 km box. See the audit.

## Reproduction

```powershell
.\.venv\Scripts\python scripts\download_lade_p_jilin.py
```

The script exits with status 1 if the SHA-256 or byte size differs from the published LFS object. It does not synthesize a replacement table.
