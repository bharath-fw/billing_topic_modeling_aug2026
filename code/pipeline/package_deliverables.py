"""Package the current business deliverables (xlsx, MoM counts CSV, HTML reports)
into one self-describing zip:

    BRIGHTSPEED_billing_payments_deliverables_<date>.zip
    ├── 00_README.html / 00_README.txt      -> guide to the package
    ├── 01_reports/
    │     ├── Brightspeed_Billing_FullYear_BI_Report.html
    │     ├── Brightspeed_Billing_Subcategory_BI_Report.html   (interactive drill-down)
    │     ├── Brightspeed_MoM_Category_Pie_Funnel.html
    │     └── Brightspeed_MoM_Subcategory_Pie_Funnel.html
    ├── 02_data_outputs/
    │     ├── billing_all_data.xlsx             (narrow cols, monthly worksheets)
    │     ├── billing_all_ytd_tagged.xlsx       (narrow + ai_tag_1..3, monthly worksheets + Overview)
    │     └── brightspeed_mom_final_tagged_counts.csv
    └── manifest.csv                            (archive_name, size, sha256, purpose)

Full scheduled year Jan 2026 - Aug 2026, 904,501 tagged billing/payments calls.
"""
from __future__ import annotations

import csv
import datetime as _dt
import hashlib
import io
import re
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "code" / "output"

DATE = _dt.date.today().strftime("%Y%m%d")
ZIP_PATH = OUT / f"BRIGHTSPEED_billing_payments_deliverables_{DATE}.zip"

TOTAL_CALLS = "904,501"

# (source, archive_name, purpose)
FILES = [
    (OUT / "Brightspeed_Billing_FullYear_BI_Report.html",
     "01_reports/Brightspeed_Billing_FullYear_BI_Report.html",
     "Macro-category BI report (KPI strip, MoM trend, 2 heatmaps, doughnut timeline, top subcategories)"),
    (OUT / "Brightspeed_Billing_Subcategory_BI_Report.html",
     "01_reports/Brightspeed_Billing_Subcategory_BI_Report.html",
     "Interactive drill-down report: pick a category to see its subcategory trend, heatmap and monthly mix"),
    (OUT / "Brightspeed_MoM_Category_Pie_Funnel.html",
     "01_reports/Brightspeed_MoM_Category_Pie_Funnel.html",
     "Month-over-month category funnel/trend dashboards (self-contained)"),
    (OUT / "Brightspeed_MoM_Subcategory_Pie_Funnel.html",
     "01_reports/Brightspeed_MoM_Subcategory_Pie_Funnel.html",
     "Month-over-month subcategory funnel/trend/heat dashboards (self-contained interactive)"),
    (OUT / "billing_all_data.xlsx",
     "02_data_outputs/billing_all_data.xlsx",
     "Every billing/payments call, narrow columns only; one worksheet per month Jan_2026..Aug_2026 + Overview"),
    (OUT / "billing_all_ytd_tagged.xlsx",
     "02_data_outputs/billing_all_ytd_tagged.xlsx",
     "MAIN DELIVERABLE: narrow + ai_tag_1/2/3 with category/subcategory; worksheets Jan_2026..Aug_2026 + Overview"),
    (OUT / "brightspeed_mom_final_tagged_counts.csv",
     "02_data_outputs/brightspeed_mom_final_tagged_counts.csv",
     "Month x macro-category volume + share of month (full YTD Jan-Aug 2026)"),
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
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>Brightspeed Billing &amp; Payments — Deliverables</title>
<style>body{{font-family:Arial,sans-serif;margin:0;background:#f6f7f8;color:#222}}
.wrap{{max-width:1100px;margin:0 auto;padding:30px}}
.hero{{background:#fff;padding:24px 28px;border-left:7px solid #512D6D;border-radius:12px}}
h1{{margin:0 0 6px;font-size:26px}} p{{color:#555;margin:6px 0}}
table{{border-collapse:collapse;width:100%;background:#fff;margin-top:18px}}
th,td{{text-align:left;padding:9px 12px;border-bottom:1px solid #e5e5e5;vertical-align:top}}
th{{background:#f3f0f6;color:#512D6D}}
a{{color:#512D6D}}</style></head><body><div class="wrap">
<div class="hero"><h1>Brightspeed Billing &amp; Payments — BI &amp; Data Deliverables</h1>
<p><b>Full scheduled year:</b> Jan 2026 – Aug 2026 &nbsp;·&nbsp; <b>{TOTAL_CALLS} billing/payments calls</b>, locally AI-tagged on GPU
&nbsp;·&nbsp; Regenerated <b>{_dt.date.today().isoformat()}</b> from the full August source file.</p>
<p>Open <b>01_reports/Brightspeed_Billing_FullYear_BI_Report.html</b> for the macro BI report and
<b>01_reports/Brightspeed_Billing_Subcategory_BI_Report.html</b> for the interactive category drill-down.
All HTML is self-contained (Plotly embedded — no internet needed).</p></div>
<table><tr><th>File</th><th>Size</th><th>Purpose</th></tr>{tr}</table>
<p style="color:#777;font-size:12px;margin-top:16px">Manifest with SHA-256 hashes: <code>manifest.csv</code>.
Large files: the tagged XLSX (~360 MB) and the narrow XLSX (~280 MB) are the data deliverables.</p>
</div></body></html>"""


def main() -> None:
    rows = []
    with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED, compresslevel=1) as z:
        for src, arc, purpose in FILES:
            if not src.exists():
                print(f"!! missing {src}")
                continue
            z.write(src, arc)
            rows.append({"name": arc, "size": f"{src.stat().st_size:,}",
                         "sha256": sha256(src), "purpose": purpose})
        readme_html = build_readme_html(rows)
        z.writestr("00_README.html", readme_html)
        txt = re.sub(r"<style>.*?</style>", "", readme_html, flags=re.S)
        txt = re.sub(r"<.*?>", " ", txt)
        txt = "\n".join(line.strip() for line in txt.splitlines() if line.strip())
        z.writestr("00_README.txt", txt)
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["archive_name", "size_bytes", "sha256", "purpose"])
        for r in rows:
            w.writerow([r["name"], r["size"].replace(",", ""), r["sha256"], r["purpose"]])
        z.writestr("manifest.csv", buf.getvalue())
    print(f"Deliverables package written: {ZIP_PATH} ({ZIP_PATH.stat().st_size/1e6:.1f} MB, {len(rows)} artifacts)")


if __name__ == "__main__":
    main()