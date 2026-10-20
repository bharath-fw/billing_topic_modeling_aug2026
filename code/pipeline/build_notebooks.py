"""Build the notebooks for the full-year reprocessing pipeline."""
from __future__ import annotations

from pathlib import Path

import nbformat as nbf

ROOT = Path(__file__).resolve().parents[2]
NB_DIR = ROOT / "code" / "notebooks"
NB_DIR.mkdir(parents=True, exist_ok=True)


def md(s: str) -> dict:
    return nbf.v4.new_markdown_cell(s)


def code(s: str) -> dict:
    return nbf.v4.new_code_cell(s)


# --------------------------------------------------------------------------- 01
nb1 = nbf.v4.new_notebook()
nb1.cells = [
    md("# Brightspeed Billing & Payments — Full-Year Reprocessing (Steps 1–3)\n\n"
       "Reprocesses the full scheduled year (Jan 2026 → Aug 24 2026) of Brightspeed "
       "call-center data, keeping **only billing & payments** lines, into aligned parquet "
       "datasets for downstream tagging and BI."),
    md("## 1. Raw string parquet (all columns aligned)\n\n"
       "`pipeline/ingest.py` streams each monthly `*_All_Call_Data.xlsx` in read-only mode, "
       "aligns every month onto one union schema, and coerces all columns to `str`."),
    code(
        "import pandas as pd\n"
        "raw = pd.read_parquet('code/data/raw_all_string.parquet')\n"
        "print('raw rows/cols:', raw.shape)\n"
        "print('all-string:', all(str(t) in ('object','string') for t in raw.dtypes))\n"
        "raw.head(2)"
    ),
    md("## 2. Billing & Payments dataset\n\n"
       "Keep rows whose `Primary Call Reason` is one of the billing categories."),
    code(
        "from code_local.pipeline import billing_narrow as BN\n"
        "billing = pd.read_parquet('code/data/billing_all.parquet')\n"
        "print('billing rows:', len(billing))\n"
        "print(billing['Primary Call Reason'].value_counts().to_string())"
    ),
    md("## 3. Narrow billing/payments parquet\n\n"
       "The exact columns used for ChatGPT-Excel tagging and the BI report."),
    code(
        "narrow = pd.read_parquet('code/data/billing_narrow.parquet')\n"
        "print('narrow shape:', narrow.shape)\n"
        "print(narrow.columns.tolist())\n"
        "print(narrow['Call_Month'].value_counts().sort_index().to_string())"
    ),
    md("## Summary\n\n"
       "`raw_all_string.parquet` → `billing_all.parquet` → `billing_narrow.parquet`.\n"
       "The narrow dataset feeds the monthly tagging workbook (step 6) and the report (step 7)."),
]
nb1.metadata = {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}}

# --------------------------------------------------------------------------- 02
nb2 = nbf.v4.new_notebook()
nb2.cells = [
    md("# Taxonomy Coverage Validation (Step 4)\n\n"
       "Check whether the governed 104-leaf billing taxonomy (`code/artifacts/taxonomy.json`) "
       "is *representatively good enough* to cover the reprocessed billing/payments narratives.\n\n"
       "**Method:** 20% random sample → one structured narrative per call\n"
       "`Customer Intent Tag | Problem Identified Tag | Reason | Summary` → embedded with "
       "**BAAI/bge-large-en-v1.5** → matched to the 104 leaf prototypes (each = mean of its "
       "10 curated centroid embeddings) via cosine similarity. Covered when max-sim ≥ 0.30."),
    code(
        "import json, pandas as pd\n"
        "OUT='code/output'\n"
        "try:\n"
        "    rep = json.load(open(f'{OUT}/coverage_report.json'))\n"
        "except FileNotFoundError:\n"
        "    import sys; sys.path.insert(0,'code/pipeline')\n"
        "    import coverage as C\n"
        "    rep = C.run(frac=0.20, threshold=0.30, device='cuda')  # may take ~20-30min on GPU\n"
        "    json.dump(rep, open(f'{OUT}/coverage_report.json','w'), indent=2)\n"
        "for k in ('n_samples','n_covered','n_fallback','coverage_pct','fallback_pct',\n"
        "          'mean_best_sim','median_best_sim'):\n"
        "    print(f'{k:14}: {rep[k]}')"
    ),
    md("## Coverage by macro category"),
    code(
        "cat = pd.DataFrame(rep['category_coverage'])\n"
        "print(cat.sort_values('calls', ascending=False).to_string(index=False))"
    ),
    md("## Coverage by leaf (top volume)"),
    code(
        "leaf = pd.DataFrame(rep['leaf_coverage']).sort_values('calls', ascending=False)\n"
        "print('\\n'.join('%-42s %7d calls  %5.1f%% covered' % (r['canonical_tag'], r['calls'], r['coverage_pct'])\n"
        "               for _, r in leaf.head(15).iterrows()))\n"
        "print('\\n... lowest coverage leaves:')\n"
        "low = leaf[leaf['calls']>=20].sort_values('coverage_pct').head(10)\n"
        "print('\\n'.join('%-42s %7d calls  %5.1f%% covered' % (r['canonical_tag'], r['calls'], r['coverage_pct'])\n"
        "               for _, r in low.iterrows()))"
    ),
    md("## Review the most-uncovered narratives"),
    code(
        "pd.DataFrame(rep['uncovered_review'])[['record_id','Call_Month','_sim','_tag','_cat','narrative']]"
    ),
    md("## Conclusion\n"
       "If `coverage_pct` is high (e.g. ≥ 90%) and the uncovered sample shows genuine "
       "billing reasons already represented by existing leaves, the taxonomy is "
       "**sufficient and kept unchanged**. If low-coverage leaves reveal recurring "
       "unmatched billing reasons, propose new canonical leaves through the governance loop."),
]
nb2.metadata = {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}}

for name, nb in [("01_full_year_reprocessing.ipynb", nb1),
                 ("02_taxonomy_coverage_validation.ipynb", nb2)]:
    nbf.write(nb, NB_DIR / name)
    print("wrote", NB_DIR / name)
