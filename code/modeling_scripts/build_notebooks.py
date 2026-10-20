"""Generate the explanatory notebooks for the v2 pipeline.

  python scripts/build_notebooks.py

Produces notebooks/01_billing_taxonomy_mining.ipynb — a fully-explained primer
that walks through every stage: data -> billing kernel -> clustering comparison
-> taxonomy mining -> GLVQ -> SOM -> scoring.  All heavy steps are cache-aware,
so re-running the notebook after the pipeline has been built is fast.
"""
from __future__ import annotations

import nbformat as nbf
from nbformat.v4 import new_code_cell, new_markdown_cell, new_notebook

NB_PATH = "/home/seshu/topic_modeling_v2/topic_modeling_v2/notebooks/01_billing_taxonomy_mining.ipynb"

md = new_markdown_cell
code = new_code_cell

C = []

C.append(md("""\
# Brightspeed Billing — Taxonomy Mining & Topic Modeling (v2)

**What this notebook does.** 7 months of Brightspeed call data (Jan–Jul 2026) are
turned into a *self-organized* billing taxonomy. Every step runs on **BGE-large
embedding vectors** (`BAAI/bge-large-en-v1.5`, 1024-d); text/keywords are used
*only to name and describe* the mined topics afterwards.

The seed taxonomy files are reference material only — we never copy their labels.

```
 YTD calls (5.0M)                        billing rows (~0.8M)
   │  collation: Root Cause + Reason        │  mined on embeddings only
   ▼                                        ▼
 heuristic Billing/Payments label ──▶ Billing Kernel (P/R/F1 tuned)
                                            │
                                            ▼
                  K-Means on BGE embeddings (silhouette-tuned, 40 clusters)
                                            │
                                            ▼
               leaf topics (keywords + representative text per cluster)
                                            │  agglomerative on centroids
                                            ▼
              2-level taxonomy  (Category ▸ Subcategory)   ── mined, not seed
                                            │
                       ┌────────────────────┼────────────────────┐
                       ▼                    ▼                    ▼
                    GLVQ (90/10)         SOM 20x20            top-3 scoring
                  prototype model      cell keywords          → XLSX
                                          + 3D topography
```
"""))

C.append(md("""\
## 0. Imports, paths, config

Everything lives in `src/` (shared modules) — the same code paths the batch
scripts use.
"""))
C.append(code("""\
import json, sys
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path.cwd().parent if Path.cwd().name == "notebooks" else Path.cwd()
sys.path.insert(0, str(ROOT))

from src import pipeline as P
from src import clustering as C
from src import taxonomy_mining as TM
from src import viz
from src.billing_kernel import BillingKernel
from src.config import ARTIFACTS_DIR, CACHE_DIR, DATA_DIR, OUTPUTS_DIR, SEED
from src.lvq import GLVQ
from src.som import KohonenSOM

print("ok · artifacts:", ARTIFACTS_DIR)
"""))

C.append(md("""\
## 1. The ML training dataset

Seven months of calls, one row per call. We keep only the columns the pipeline
needs:

| Column | Meaning |
|---|---|
| `ytd_call_id` | unique call id across months |
| `ban` | billing account number |
| `network_type` | fiber / DSL / ... |
| `record_id` | source record id |
| `category` | heuristic `Primary Call Reason` |
| `call_intent` | **collation of Root Cause + Reason** (the text we model) |
| `month` / `year_month` / `call_date` | source + actual call dates |

Embeddings are computed on the **whole short string** — no sentence splitting:
`embedding_model.encode("Customer upset about delayed shipping refund")`.
"""))
C.append(code("""\
df = P.load_ml_dataset()
df = P.add_heuristic_label(df)
df.head(3)
print("\\ntotal rows:", len(df))
print(df["month"].value_counts().sort_index().to_string())
print("\\nbilling heuristic label (Primary Call Reason in {Billing, Payments}):")
print(df["billing_heuristic"].value_counts().to_string())
"""))

C.append(md("""\
## 2. Stage A — Billing / Non-Billing segmentation kernel

The first narrow is: *is this call billing-related?*  We train a binary
classifier on BGE embeddings using the heuristic `Billing`/`Payments` Primary
Call Reason signal as the label, then tune a decision threshold on a held-out
10% to maximise F1.  The saved kernel can then segment *any* call text.
"""))
C.append(code("""\
kernel = BillingKernel.load(ARTIFACTS_DIR / "billing_kernel.joblib")
print(json.dumps(kernel.metrics, indent=2))
"""))

C.append(md("""\
## 3. Stage B — prune the billing segment

We predict billing on a mixed sample, keep only the billing rows, and carry their
embeddings forward.  **Every later step (clustering, mining, LVQ, SOM) touches
only these billing lines.**
"""))
C.append(code("""\
seg = pd.read_parquet(ARTIFACTS_DIR / "billing_segment_sample.parquet")
X = np.load(CACHE_DIR / "emb_candidate_120k.npy")[: len(seg)]
print("billing segment:", len(seg), "rows · embeddings:", X.shape)
print(seg["month"].value_counts().sort_index().to_string())
"""))

C.append(md("""\
## 4. Stage C — which clustering algorithm grooms the taxonomy best?

We compare candidates on the **billing embeddings** using criteria that matter
for taxonomy grooming: silhouette (cohesion/separation), coverage, per-month
stability, and how well each cluster maps to a seed topic
(interpretability).  K-Means wins on this data: full coverage, best silhouette,
and the most stable silhouette across all 7 months.
"""))
C.append(code("""\
table = pd.read_json(ARTIFACTS_DIR / "clustering_comparison_table.json")
print(table.round(4).to_string())
best = C.choose_best(table)
print(f"\\nrecommended algorithm for taxonomy grooming: {best}")
"""))

C.append(md("""\
## 5. Stage D — mine the self-organized taxonomy

`taxonomy_mining.mine()` does the grooming:

1. fine K-Means clusters on the embeddings (40 clusters, silhouette-tuned);
2. every cluster becomes a **leaf topic** — named from its *own* representative
   text, described by its *own* top TF-IDF keywords (display only);
3. cluster centroids are agglomeratively grouped into coarse **categories**.

Clusters too small to trust fold into `Other Category :: Misc/Other`.
"""))
C.append(code("""\
mined = json.loads((DATA_DIR / "taxonomy_mined.json").read_text())
n_cat = len(mined["categories"])
n_sub = sum(len(c["subcategories"]) for c in mined["categories"])
print(f"mined taxonomy: {n_cat} categories, {n_sub} subcategories")
for cat in mined["categories"][:4]:
    print("\\n▍ " + cat["name"] + f"  ({cat['count']:,} calls)")
    for s in cat["subcategories"][:4]:
        print(f"   • {s['name']}  [{s['count']:,}]  kw={s['keywords']}")
"""))

C.append(md("""\
## 6. Stage E — GLVQ prototype model (90/10, validated)

Generalised LVQ refines one prototype per mined leaf so leaves separate
maximally while keeping coverage.  It is trained on a **90/10 split** and its
held-out accuracy is reported.  The trained model is what we score with.
"""))
C.append(code("""\
model = GLVQ.load(ARTIFACTS_DIR / "glvq.joblib")
active = json.loads((ARTIFACTS_DIR / "glvq_active_keys.json").read_text())
print("active leaves:", len(active["active_keys"]))
print("prototypes:", model.prototypes_.shape)
top, sim, prob = model.predict_proba_topk(X[:2000], 3)
print("mean top-1/2/3 confidence:", prob.mean(0).round(3))
"""))

C.append(md("""\
## 7. Stage F — Kohonen SOM 20x20 + 3D topography

The SOM projects the billing embeddings onto a 20x20 grid.  Each call lands in
its Best-Matching Unit (BMU) cell; cells accumulate counts to form the
topographic map.  The cell table lists each cell's coordinates, call count,
top keywords, and dominant mined subcategory.
"""))
C.append(code("""\
som = KohonenSOM.load(ARTIFACTS_DIR / "som20.joblib")
density = som.accumulate_density(X)
print("cells with calls:", (density > 0).sum(), "· total:", int(density.sum()))
print("peak:", int(density.max()), "calls/cell")
cell_df = pd.read_csv(OUTPUTS_DIR / "som_cells.tsv", sep="\\t")
cell_df.head(12)
"""))

C.append(md("""\
## 8. Visualizations

Three outputs under `outputs/`:
- `treemap.png` — call volume by Category ▸ Subcategory
- `taxonomy_tree.png` — the mined 2-level hierarchy with keywords per leaf
- `som_3d.png` + `som_cells.png` — 3D topographic map and cell heat-map
"""))
C.append(code("""\
import IPython.display as d
for f in ["treemap.png", "taxonomy_tree.png", "som_3d.png"]:
    d.display(d.Image(OUTPUTS_DIR / f))
"""))

C.append(md("""\
## 9. Scoring

For each billing row we emit the top-3 Category :: Subcategory assignments with
confidence.  The full YTD scoring file is written by
`scripts/score_ytd.py` → `outputs/scoring_ytd_billing.xlsx`.
"""))
C.append(code("""\
sc = pd.read_excel(OUTPUTS_DIR / "scoring_billing_sample.xlsx",
                   sheet_name="Billing_Scoring", nrows=5)
sc[["ytd_call_id", "call_intent", "category_1", "subcategory_1", "conf_1",
    "category_2", "subcategory_2", "conf_2", "category_3", "subcategory_3", "conf_3"]]
"""))

C.append(md("""\
## 10. What changed vs. v1

| Aspect | v1 | v2 |
|---|---|---|
| Data | June only | 7 months (Jan–Jul 2026) |
| Scope | all calls | **billing only** (kernel-pruned) |
| Embeddings | all-MiniLM (384-d) | **BGE-large (1024-d)** |
| Clustering | fixed k + label hand-map | **silhouette-tuned k + algorithm comparison** |
| Taxonomy | hand-labelled classes | **mined from embeddings** (seed = reference only) |
| Model | softmax on UMAP+kmeans | **GLVQ prototypes** on raw embeddings (90/10) |
| Maps | – | **SOM 20x20** + 3D topography |
| Output | scored_intents.csv | **XLSX scoring file** + treemap + taxonomy tree |
"""))

nb = new_notebook(cells=C)
nb.metadata["kernelspec"] = {
    "display_name": "Python (topic_modeling_v2)", "language": "python",
    "name": "topic_v2"}
nb.metadata["language_info"] = {"name": "python"}
nbf.write(nb, NB_PATH)
print("wrote", NB_PATH)