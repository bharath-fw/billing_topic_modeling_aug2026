"""Build the two business-transfer XLSX workbooks from the full-year tagged parquet.

  * ``billing_all_data.xlsx``        -- the untagged billing dataset (one sheet per
                                       calendar month: Jan_2026 .. Aug_2026) carrying
                                       the narrow tagging columns; plus an Overview.
  * ``billing_all_ytd_tagged.xlsx``  -- the same rows with the nine ``ai_*`` tag
                                       columns (ai_tag_1/2/3, category, subcategory)
                                       filled by the frozen-taxonomy ML scorer.

Written to ``code/output``. Dated to the current full-year refresh (Sep 2026).
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
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


def _build(df: pd.DataFrame, out_path: Path, month_cols: list[str]) -> None:
    months = sorted(df["Call_Month"].unique())
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(out_path, engine="openpyxl") as xw:
        for m in months:
            sub = df[df["Call_Month"] == m].reset_index(drop=True)
            sheet = month_label(m)
            cols = [c for c in month_cols if c in sub.columns]
            out = sub[cols]
            out.to_excel(xw, sheet_name=sheet, index=False)
            ws = xw.sheets[sheet]
            for i, col in enumerate(out.columns, start=1):
                letter = ws.cell(row=1, column=i).column_letter
                ws.column_dimensions[letter].width = FIXED_WIDTHS.get(col, 40)
            ws.freeze_panes = "D2"
        if "ai_category_1" in df.columns:
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
        else:
            overview = df.groupby("Call_Month").size().rename("rows").reset_index()
            overview.to_excel(xw, sheet_name="Overview", index=False)
            ws = xw.sheets["Overview"]
            ws.column_dimensions[ws.cell(row=1, column=1).column_letter].width = 12
            ws.column_dimensions[ws.cell(row=1, column=2).column_letter].width = 12
    print(f"wrote {out_path} ({len(df):,} rows x {len(months)} months, "
          f"{out_path.stat().st_size/1e6:.1f} MB)")


def build(parquet_path: Path, out_dir: Path | None = None) -> None:
    out_dir = Path(out_dir) if out_dir else OUT
    out_dir.mkdir(parents=True, exist_ok=True)
    df = pd.read_parquet(parquet_path).astype(str)
    if "Call_Month" not in df.columns:
        raise SystemExit("no Call_Month column in tagged parquet")

    # untagged "data" workbook = narrow cols only
    narrow = df[NARROW_COLS].copy()
    _build(narrow, out_dir / "billing_all_data.xlsx", NARROW_COLS)

    # tagged workbook = narrow + ai_* tag cols
    cols = NARROW_COLS + TAG_ORDER
    tagged = df[cols]
    _build(tagged, out_dir / "billing_all_ytd_tagged.xlsx", cols)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--parquet", type=Path, default=OUT / "billing_tagged_full.parquet")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    build(args.parquet, args.out)
