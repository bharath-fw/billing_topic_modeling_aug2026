# Brightspeed Billing & Payments — Full-Year Reprocessing Pipeline

Reprocessing of the latest Brightspeed (US fiber ISP) call-center data across the full
scheduled year (Jan 2026 → Aug 24, 2026) — **billing & payments only**.

This pipeline turns the raw monthly XLSX dump into clean, aligned, model-ready datasets,
validates the mined billing taxonomy for coverage, produces a monthly tagging workbook +
a guided ChatGPT-Excel classifier prompt, and renders a static self-contained HTML BI
report.

---

## Deliverables

| # | Step | Output | Location |
|--:|------|--------|----------|
| 1 | Raw string parquet (all columns aligned) | `raw_all_string.parquet` | `code/data/` |
| 2 | Billing/payments parquet (`Primary Call Reason` ∈ {Billing, Payments}) | `billing_all.parquet` | `code/data/` |
| 3 | Narrow billing/payments parquet | `billing_narrow.parquet` | `code/data/` |
| 4 | Taxonomy coverage validation (20% sample, BAAI bge-large) | `coverage_report.json`, `coverage_by_category.csv`, `coverage_by_leaf.csv` | `code/output/` |
| 5 | (Validated existing taxonomy — no change needed) | `artifacts/taxonomy.json` | `code/artifacts/` |
| 6 | Clean tagging workbook + guided plugin prompt | `billing_tagging_input.xlsx`, `ChatGPT_Plugin_Guided_Prompt.md` | `code/output/` |
| 7 | Static HTML BI report | `Brightspeed_Billing_BI_Report.html` | `code/output/` |

---

## How to run (Docker)

```bash
cd code/docker
docker compose build
docker compose --profile taxonomy run --rm taxonomy ../pipeline/ingest.py --out ../data/raw_all_string.parquet
docker compose --profile taxonomy run --rm taxonomy ../pipeline/billing_narrow.py
docker compose --profile taxonomy run --rm taxonomy \
    ../pipeline/coverage.py --frac 0.20 --threshold 0.30 --device cuda
docker compose --profile taxonomy run --rm taxonomy ../pipeline/build_xlsx.py
docker compose --profile taxonomy run --rm taxonomy ../pipeline/prompt_gen.py
docker compose --profile taxonomy run --rm taxonomy \
    ../pipeline/report.py ../input_output/billing_all_ytd_tagged.xlsx
```

Local (no Docker) with a Python 3.10+ venv and the packages in `docker/requirements.txt`:

```bash
python code/pipeline/ingest.py --out code/data/raw_all_string.parquet
python code/pipeline/billing_narrow.py
python code/pipeline/coverage.py --frac 0.20 --device cuda   # GPU; omit --device for CPU
python code/pipeline/build_xlsx.py
python code/pipeline/prompt_gen.py
python code/pipeline/report.py <tagged.xlsx>
```

Every stage is also available as a notebook (see `code/notebooks/`).

---

## Pipeline notes

### 1 — Raw string parquet
`pipeline/ingest.py` streams each monthly `*_All_Call_Data.xlsx` in read-only mode
(openpyxl) — pandas-loading the multi-hundred-MB files is far too slow. It aligns every
month onto a single union schema, coerces **all** columns to `str`, records `Source`
and adds parsed `Call_Date` / `Call_Month`. An Excel artifact column (a leaked
`=MIN(...)` cell in the August file) is dropped.

**Result: 4,175,648 rows × 24 columns.**

> Data-quality note: the July file is truncated at Excel's 1,048,575-row limit and ~54%
> of its `Start Time Date` cells are `NaT`, so July's month breakdown under-counts.
> This is a source-file limitation, preserved as-is in the raw parquet.

### 2 & 3 — Billing/payments datasets
`pipeline/billing_narrow.py` keeps rows whose `Primary Call Reason` is `Billing` or
`Payments`, then projects to the narrow tagging schema:

`BAN, record_id, Call_Date, Call_Month, Customer Intent Tag, Problem Identified Tag,
Reason, Summary, Queue Category, Conversation ID, QueueName`

**Result: 881,057 billing/payments rows** (Billing 550,720 · Payments 330,337) across
8 calendar months.

### 4 — Taxonomy coverage validation
`pipeline/coverage.py` samples **20%** (176,211 calls), builds one structured narrative
per call by concatenating
`Customer Intent Tag | Problem Identified Tag | Reason | Summary`,
embeds it with **BAAI/bge-large-en-v1.5** (1024-d, GPU), and matches against the 104
taxonomy leaves (each leaf = mean of its up-to-10 curated centroid embeddings). A call
is "covered" when its nearest-leaf cosine similarity ≥ `0.30`. Coverage is reported
overall, by macro category, and by leaf, with a sample of the most-uncovered narratives
for human review. Summary:
- **Coverage %** and fallback % (see `coverage_report.json`)
- Category / leaf tables: `coverage_by_category.csv`, `coverage_by_leaf.csv`

### 5 — Taxonomy
The existing governed 104-leaf taxonomy (`code/artifacts/taxonomy.json` +
`canonical_vocabulary.csv`) was validated and **kept unchanged** (it already covers
billing & payments — step 4 confirmed representative coverage). Partial/tag revision is
only needed if the coverage report signals weak coverage, and would follow the existing
governance loop.

### 6 — Clean workbook + guided prompt
`pipeline/build_xlsx.py` writes **`billing_tagging_input.xlsx`** with **one worksheet per
calendar month** (Jan_2026 … Aug_2026) plus an `Overview` sheet, each carrying the narrow
columns plus pre-created empty `ai_tag_1/2/3` (+ category/subcategory) output columns, so
the classifier only fills values. `pipeline/prompt_gen.py` emits the
**`ChatGPT_Plugin_Guided_Prompt.md`** — a controlled-vocabulary (104 tags, 11 categories)
prompt generated from `canonical_vocabulary.csv` that instructs batch-per-worksheet
classification with anti-drift and specificity rules.

> The actual tagging is an **offline** step run by a business user in ChatGPT/Excel on
> `billing_tagging_input.xlsx`; the tagged workbook is then fed to step 7.

### 7 — Static HTML BI report
`pipeline/report.py` is a generic **report app**: point it at any tagged workbook (monthly
worksheets **or** a single tagged sheet with a month + `category_1`/`ai_tag_1` column) and
it emits a **self-contained static HTML** (Plotly offline, no CDN) containing:
- KPI strip (calls, months, categories, fallback share)
- Month-over-month grouped-bar trend by macro category
- Temporal heatmaps (month × category) — volume and share
- Doughnut/pie **funnel across a horizontal timeline** (one doughnut per month)
- Top-subcategory trend lines

The demo report was generated from the existing `code/input_output/billing_all_ytd_tagged.xlsx`
(the "cached existing" tagged file), per the offline-tagging assumption.

<br>
<p align="center"><code>Brightspeed Billing & Payments · full-year reprocessing</code></p>
