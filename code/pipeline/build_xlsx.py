"""Step 6a: Build a clean XLSX with one worksheet per calendar month.

This is the *tagging input* workbook for the ChatGPT Excel plugin (step 6b).
Each worksheet corresponds to one calendar month of billing/payments calls and
carries exactly the columns of the narrow parquet, so the plugin can classify
each month's rows as one independent batch (small enough for reliable inference).

After the plugin writes the classification columns back (ai_tag_1 / ai_category_1 /
ai_subcategory_1 and optional ranks 2–3) into each month worksheet, the workbook is
the "tagged" file that feeds step 7 (the HTML BI report).
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "code" / "data"
OUT = ROOT / "code" / "output"

NARROW_COLS = [
    "BAN", "record_id", "Call_Date", "Call_Month", "Customer Intent Tag",
    "Problem Identified Tag", "Reason", "Summary", "Queue Category",
    "Conversation ID", "QueueName",
]

# Columns the ChatGPT plugin should add (these are written empty so the workbook
# has stable, pre-named columns and the plugin only has to fill values).
TAG_OUTPUT_COLS = [
    "ai_tag_1", "ai_category_1", "ai_subcategory_1",
    "ai_tag_2", "ai_category_2", "ai_subcategory_2",
    "ai_tag_3", "ai_category_3", "ai_subcategory_3",
]

FIXED_WIDTHS = {
    "BAN": 14, "record_id": 20, "Call_Date": 12, "Call_Month": 12,
    "Customer Intent Tag": 30, "Problem Identified Tag": 30,
    "Reason": 60, "Summary": 70, "Queue Category": 20,
    "Conversation ID": 36, "QueueName": 24,
    "ai_tag_1": 40, "ai_category_1": 38, "ai_subcategory_1": 38,
    "ai_tag_2": 40, "ai_category_2": 38, "ai_subcategory_2": 38,
    "ai_tag_3": 40, "ai_category_3": 38, "ai_subcategory_3": 38,
}


def month_label(ym: str) -> str:
    return pd.Timestamp(ym + "-01").strftime("%b_%Y")


def build_workbook(narrow_path: Path, out_path: Path,
                   include_tag_cols: bool = True) -> None:
    df = pd.read_parquet(narrow_path)
    df = df.astype(str)
    months = sorted(df["Call_Month"].unique())
    if not months or months == [""]:
        raise SystemExit("no usable Call_Month values; cannot split by month")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(out_path, engine="openpyxl") as xw:
        for m in months:
            sub = df[df["Call_Month"] == m].reset_index(drop=True)
            sheet = month_label(m)
            cols = list(NARROW_COLS)
            if include_tag_cols:
                cols += TAG_OUTPUT_COLS
            out = pd.DataFrame({c: (sub[c] if c in sub.columns else "") for c in cols})
            out.to_excel(xw, sheet_name=sheet, index=False)
            # fixed, content-aware column widths (per-cell autosizing is O(rows) and
            # far too slow for 100k+-row sheets)
            ws = xw.sheets[sheet]
            for i, col in enumerate(out.columns, start=1):
                ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = \
                    FIXED_WIDTHS.get(col, 40)
            ws.freeze_panes = "D2"
        # All-Month overview sheet
        overview = df.groupby("Call_Month").size().rename("rows").reset_index()
        overview.to_excel(xw, sheet_name="Overview", index=False)
    print(f"XLSX written ({len(df):,} rows across {len(months)} months) -> {out_path}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--narrow", type=Path, default=DATA / "billing_narrow.parquet")
    ap.add_argument("--out", type=Path, default=OUT / "billing_tagging_input.xlsx")
    ap.add_argument("--no-tag-cols", action="store_true",
                    help="do not pre-add the ai_tag_* output columns")
    args = ap.parse_args()
    build_workbook(args.narrow, args.out, include_tag_cols=not args.no_tag_cols)


if __name__ == "__main__":
    main()
