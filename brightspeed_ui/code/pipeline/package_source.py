"""Package the end-to-end source code (collation -> filtering -> ML scoring)
for a code handoff:

    BRIGHTSPEED_billing_pipeline_source_<date>.zip
    ├── README.md                       how to run each stage
    ├── manifest.csv                    archive_name, size, sha256, purpose
    ├── notebooks/
    │     ├── 01_full_year_reprocessing.ipynb
    │     └── 02_taxonomy_coverage_validation.ipynb
    ├── pipeline/
    │     ├── ingest.py                 collate all source xlsx -> raw parquet
    │     ├── billing_narrow.py          filter to Billing & Payments -> narrow parquet
    │     ├── coverage.py                build narratives, leaf prototypes, coverage checks
    │     ├── autotag.py                 ML scoring on GPU -> tagged parquet
    │     └── requirements.txt
    └── models/
          ├── coverage_leaf_order.csv    frozen 104-leaf taxonomy order
          └── coverage_leaf_protos.npy   frozen leaf prototype embeddings (BGE 1024-d)
"""
from __future__ import annotations

import csv
import datetime as _dt
import hashlib
import io
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "code" / "output"
PIPE = ROOT / "code" / "pipeline"

DATE = _dt.date.today().strftime("%Y%m%d")
ZIP_PATH = OUT / f"BRIGHTSPEED_billing_pipeline_source_{DATE}.zip"

FILES = [
    (ROOT / "code/notebooks/01_full_year_reprocessing.ipynb",
     "notebooks/01_full_year_reprocessing.ipynb",
     "Step 1-3 walkthrough: collate source xlsx -> raw string parquet -> billing filter -> narrow parquet"),
    (ROOT / "code/notebooks/02_taxonomy_coverage_validation.ipynb",
     "notebooks/02_taxonomy_coverage_validation.ipynb",
     "Step 4 walkthrough: score narratives against the frozen taxonomy and review coverage"),
    (PIPE / "ingest.py", "pipeline/ingest.py",
     "Collation: read every datasets/*.xlsx into one all-string parquet"),
    (PIPE / "billing_narrow.py", "pipeline/billing_narrow.py",
     "Filtering: keep Billing & Payments lines, write billing_all + billing_narrow parquets"),
    (PIPE / "coverage.py", "pipeline/coverage.py",
     "Scoring helpers: narratives, frozen leaf prototypes, cosine coverage validation"),
    (PIPE / "autotag.py", "pipeline/autotag.py",
     "ML scoring: embed each narrative (BAAI/bge-large-en-v1.5), cosine vs prototypes, assign ai_tag_1/2/3"),
    (ROOT / "code/docker/requirements.txt", "pipeline/requirements.txt",
     "Python dependencies (pandas, pyarrow, openpyxl, sklearn, sentence-transformers, torch, plotly, ...)"),
    (OUT / "coverage_leaf_order.csv", "models/coverage_leaf_order.csv",
     "Frozen taxonomy: 104 leaves (canonical_tag, category, subcategory)"),
    (OUT / "coverage_leaf_protos.npy", "models/coverage_leaf_protos.npy",
     "Frozen taxonomy: 104 x 1024-d prototype embeddings used for scoring"),
]

README = """# Brightspeed Billing & Payments - end-to-end pipeline source

## Stages
1. COLLATE  pipeline/ingest.py      reads datasets/*.xlsx -> raw_all_string.parquet
2. FILTER   pipeline/billing_narrow.py -> billing_all.parquet + billing_narrow.parquet
3. SCORE    pipeline/autotag.py     ML tags every narrative -> billing_tagged_full.parquet
4. VALIDATE notebooks/02            cosine coverage of the frozen taxonomy (threshold 0.30)

## Filters applied (billing_narrow.py)
- Row filter: keep only calls whose trimmed Primary Call Reason is "Billing" or
  "Payments" (everything else is dropped). YTD this is 904,501 of ~4,262,719 records.
- Column filter: keep only the 11 narrow columns used for tagging - BAN, record_id,
  Call_Date, Call_Month, Customer Intent Tag, Problem Identified Tag, Reason,
  Summary, Queue Category, Conversation ID, QueueName.
- All values are coerced to string.
- ingest.py also drops any formula columns (names starting with "=").

## Run (from the repo root, plain Python or Docker)
    python pipeline/ingest.py  --out code/data/raw_all_string.parquet
    python pipeline/billing_narrow.py --raw code/data/raw_all_string.parquet \\
        --out-billing code/data/billing_all.parquet \\
        --out-narrow code/data/billing_narrow.parquet
    python pipeline/autotag.py --device cuda \\
        --out code/output/billing_tagged_full.parquet

Docker (GPU image built from these requirements):
    docker run --rm --gpus all -v $PWD:/work brightspeed-taxonomy:latest \\
        python pipeline/autotag.py --device cuda

## Notes
- Scoring uses the FROZEN taxonomy in models/: coverage_leaf_order.csv (104 leaves,
  11 categories) + coverage_leaf_protos.npy (embeddings, 1024-d). Do not regenerate
  retraining; scoring is cosine similarity vs these frozen prototypes.
- Embedding model: BAAI/bge-large-en-v1.5 (downloaded on first run).
- autotag.py parameters (do not change for consistency): THRESHOLD=0.30,
  MAX_CHARS=700, batched on GPU. Large runs take a few hours on an 8 GB GPU.
- notebooks/01 references the repo layout (code/data, code/output); place this
  folder as .../code inside the repo, or run the pipeline scripts as shown above.
"""


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    rows = []
    with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for src, arc, purpose in FILES:
            if not src.exists():
                print(f"!! missing {src}")
                continue
            z.write(src, arc)
            rows.append({"name": arc, "size": f"{src.stat().st_size:,}",
                         "sha256": sha256(src), "purpose": purpose})
        z.writestr("README.md", README)
        z.writestr("manifest.csv", _manifest_csv(rows))
    print(f"Source package written: {ZIP_PATH} ({ZIP_PATH.stat().st_size/1e6:.1f} MB, {len(rows)} files)")


def _manifest_csv(rows: list[dict]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["archive_name", "size_bytes", "sha256", "purpose"])
    for r in rows:
        w.writerow([r["name"], r["size"].replace(",", ""), r["sha256"], r["purpose"]])
    return buf.getvalue()


if __name__ == "__main__":
    main()