"""Build a tagged XLSX (one worksheet per month) from the locally autotagged parquet.

Reuses the same monthly-worksheet layout as :mod:`build_xlsx` but with the nine
``ai_*`` classification columns *filled* by the on-GPU local tagger
(:mod:`autotag`), plus an ``Overview`` sheet summarising the month x category mix.

Output: ``code/output/billing_tagged_full.xlsx``
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
TAG_ORDER = [f"ai_{k}_{r}"
             for r in (1, 2, 3)
             for k in ("tag", "category", "subcategory")]

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


def build_tagged_xlsx(parquet_path: Path, out_path: Path) -> None:
    df = pd.read_parquet(parquet_path).astype(str)
    months = sorted(df["Call_Month"].unique())
    if not months or months == [""]:
        raise SystemExit("no usable Call_Month values; cannot split by month")

    cols = NARROW_COLS + TAG_ORDER
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise SystemExit(f"missing columns in tagged parquet: {missing}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(out_path, engine="openpyxl") as xw:
        for m in months:
            sub = df[df["Call_Month"] == m].reset_index(drop=True)
            sheet = month_label(m)
            out = sub[cols]
            out.to_excel(xw, sheet_name=sheet, index=False)
            ws = xw.sheets[sheet]
            for i, col in enumerate(out.columns, start=1):
                ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = \
                    FIXED_WIDTHS.get(col, 40)
            ws.freeze_panes = "D2"
        overview = (df.groupby(["Call_Month", "ai_category_1"]).size()
                    .rename("calls").reset_index())
        total = df.groupby("Call_Month").size().rename("total_calls").reset_index()
        overview = overview.merge(total, on="Call_Month").sort_values(
            ["Call_Month", "calls"], ascending=[True, False])
        overview.to_excel(xw, sheet_name="Overview", index=False)
        ws = xw.sheets["Overview"]
        for i, col in enumerate(overview.columns, start=1):
            ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = \
                {"Call_Month": 12, "ai_category_1": 40, "calls": 12,
                 "total_calls": 12}.get(col, 20)
    print(f"Tagged XLSX written ({len(df):,} rows across {len(months)} months) -> {out_path}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--parquet", type=Path,
                    default=OUT / "billing_tagged_full.parquet")
    ap.add_argument("--out", type=Path, default=OUT / "billing_tagged_full.xlsx")
    args = ap.parse_args()
    build_tagged_xlsx(args.parquet, args.out)


if __name__ == "__main__":
    main()
