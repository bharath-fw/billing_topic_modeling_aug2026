"""Assemble a business-facing "knowledge-transfer" zipped package.

Gathers every deliverable from the Brightspeed billing/payments reprocessing +
local GPU autotagging pipeline into one self-describing zip:

    BRIGHTSPEED_billing_payments_KT_<date>.zip
    ├── 00_README.html              -> opening guide to the package (also .md source)
    ├── 01_billing_bi_report_full_year.html       # 8-month report (autotagged)
    ├── 01_billing_bi_report_demo_cached.html     # 7-month demo (cached tagged file)
    ├── 02_notebooks/
    │     ├── 01_full_year_reprocessing.html
    │     └── 02_taxonomy_coverage_validation.html
    ├── 03_data_outputs/
    │     ├── billing_tagged_full.xlsx            # main business deliverable
    │     ├── billing_tagged_summary.csv
    │     └── (all coverage_* report files)
    ├── 04_governance/
    │     └── ChatGPT_Plugin_Guided_Prompt.md     # tagging guidance for humans
    └── manifest.csv                              # every file: path, size, hash, purpose
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "code" / "output"
DATA = ROOT / "code" / "data"
ART = ROOT / "code" / "artifacts"
NBHTML = Path("/tmp/opencode/nb_html")

DATE = _dt.date.today().strftime("%Y%m%d")
ZIP_PATH = OUT / f"BRIGHTSPEED_billing_payments_KT_{DATE}.zip"

# (source, archive_name, purpose)
FILES = [
    # reports
    (OUT / "Brightspeed_Billing_FullYear_BI_Report.html",
     "01_billing_bi_report_full_year.html",
     "8-month static BI report built from locally autotagged calls (self-contained HTML, Charts enabled)"),
    # notebooks
    (NBHTML / "01_full_year_reprocessing.html",
     "02_notebooks/01_full_year_reprocessing.html",
     "HTML render of pipeline notebook #1: raw ingest -> billing filters -> narrow parquet"),
    (NBHTML / "02_taxonomy_coverage_validation.html",
     "02_notebooks/02_taxonomy_coverage_validation.html",
     "HTML render of notebook #2: 104-leaf taxonomy coverage validation (100% at 0.30 cos)"),
    # data outputs
    (OUT / "billing_tagged_full.xlsx",
     "03_data_outputs/billing_tagged_full.xlsx",
     "MAIN DELIVERABLE: one worksheet per month (Jan_2026..Aug_2026) + Overview; 881,057 locally tagged calls with ai_tag_1/2/3, category, subcategory"),
    (OUT / "billing_tagged_summary.csv",
     "03_data_outputs/billing_tagged_summary.csv",
     "Month x category volume matrix + per-month totals"),
    (OUT / "coverage_report.json",
     "03_data_outputs/coverage_report.json",
     "Coverage validation summary (n=176,211 sample, coverage 100.0%, mean best-sim 0.745)"),
    (OUT / "coverage_by_category.csv",
     "03_data_outputs/coverage_by_category.csv",
     "Per-macro-category coverage stats"),
    (OUT / "coverage_by_leaf.csv",
     "03_data_outputs/coverage_by_leaf.csv",
     "Per-leaf (104) coverage stats"),
    # governance / tagging guidance
    (OUT / "ChatGPT_Plugin_Guided_Prompt.md",
     "04_governance/ChatGPT_Plugin_Guided_Prompt.md",
     "Guided tagging prompt (104 tags / 11 categories) — for a human/LLM re-tag second pass if ever needed"),
    (ART / "canonical_vocabulary.csv",
     "04_governance/canonical_vocabulary.csv",
     "The governed 104-leaf canonical vocabulary (tag, category, subcategory, definition)"),
    (ART / "curated_centroids_10_each.csv",
     "04_governance/curated_centroids_10_each.csv",
     "10 curated centroid texts per leaf used to build leaf prototypes"),
    # docs
    (ROOT / "code" / "README.md",
     "05_docs/README.md",
     "Pipeline documentation: steps, commands, notebook + docker guidance"),
]


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build_readme_html(rows: list[dict]) -> str:
    tr = "\n".join(
        f"<tr><td>{r['name']}</td><td style='font-family:monospace'>{r['size']}</td>"
        f"<td>{r['purpose']}</td></tr>"
        for r in rows
    )
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>Brightspeed Billing & Payments — KT Package</title>
<style>body{{font-family:Arial,sans-serif;margin:0;background:#f6f7f8;color:#222}}
.wrap{{max-width:1100px;margin:0 auto;padding:30px}}
.hero{{background:#fff;padding:24px 28px;border-left:7px solid #512D6D;border-radius:12px}}
h1{{margin:0 0 6px;font-size:26px}} p{{color:#555;margin:6px 0}}
table{{border-collapse:collapse;width:100%;background:#fff;margin-top:18px}}
th,td{{text-align:left;padding:9px 12px;border-bottom:1px solid #e5e5e5;vertical-align:top}}
th{{background:#f3f0f6;color:#512D6D}}
a{{color:#512D6D}}</style></head><body><div class="wrap">
<div class="hero"><h1>Brightspeed Billing & Payments — BI &amp; Tagging Knowledge-Transfer Package</h1>
<p><b>Full scheduled year:</b> Jan 2026 – Aug 24, 2026 &nbsp;·&nbsp; <b>881,057 billing/payments calls</b>, locally AI-tagged on GPU</p>
<p>Open <b>01_billing_bi_report_full_year.html</b> for the interactive BI report (KPI strip, trend, temporal heatmaps,
monthly doughnut-funnel timeline, top-subcategory trends). All HTML is self-contained (Plotly embedded, no internet needed).</p></div>
<table><tr><th>File</th><th>Size</th><th>Purpose</th></tr>{tr}</table>
<p style="color:#777;font-size:12px;margin-top:16px">Manifest with SHA-256 hashes: <code>manifest.csv</code>. Non-HTML risks to download: the tagged XLSX (~350 MB) and tagged parquet.</p>
</div></body></html>"""


def main() -> None:
    rows = []
    with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED) as z:
        for src, arc, purpose in FILES:
            if not src.exists():
                print(f"!! missing {src}")
                continue
            z.write(src, arc)
            rows.append({"name": arc, "size": f"{src.stat().st_size:,}",
                         "sha256": sha256(src), "purpose": purpose})
        # 00_README.html + a plain .md mirror
        readme_html = build_readme_html(rows)
        z.writestr("00_README.html", readme_html)
        import re
        txt = re.sub(r"<style>.*?</style>", "", readme_html, flags=re.S)
        txt = re.sub(r"<.*?>", " ", txt)
        txt = "\n".join(line.strip() for line in txt.splitlines() if line.strip())
        z.writestr("00_README.txt", txt)
        # manifest.csv
        import io, csv
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["archive_name", "size_bytes", "sha256", "purpose"])
        for r in rows:
            w.writerow([r["name"], r["size"].replace(",", ""), r["sha256"], r["purpose"]])
        z.writestr("manifest.csv", buf.getvalue())
    print(f"KT package written: {ZIP_PATH} ({ZIP_PATH.stat().st_size/1e6:.1f} MB, {len(rows)} artifacts)")


if __name__ == "__main__":
    main()