"""Steps 2 & 3: billing/payments dataset.

Reads the concatenated raw parquet (step 1), keeps only rows whose
``Primary Call Reason`` is a billing/payment category, and (step 3) writes a
narrow dataset with the columns needed for tagging:

    BAN, Record ID (record_id), date, Customer Intent Tag, Problem Identified Tag,
    Reason, Summary, Queue Category, Conversation ID, QueueName

The desired narrower parquet carries these plus a few stable identifiers
(record_id, month) so it can feed the Excel tagging workbook and the BI report.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "code" / "data"

BILLING_CATEGORIES = {"Billing", "Payments"}

NARROW_COLS = [
    "BAN", "record_id", "Call_Date", "Call_Month", "Customer Intent Tag",
    "Problem Identified Tag", "Reason", "Summary", "Queue Category",
    "Conversation ID", "QueueName",
]


def to_col(df: pd.DataFrame, *cands: str) -> str | None:
    for c in cands:
        if c in df.columns:
            return c
    return None


def build_billing(raw_path: Path, out_billing: Path, out_narrow: Path) -> None:
    print(f"loading raw parquet: {raw_path}")
    df = pd.read_parquet(raw_path)

    prim = to_col(df, "Primary Call Reason")
    if prim is None:
        raise SystemExit("raw parquet has no 'Primary Call Reason' column")
    sub = to_col(df, "Sub Call Reason")

    # Determine billing via Primary Call Reason (normalised)
    pcr = df[prim].fillna("").str.strip()
    billing_mask = pcr.isin(BILLING_CATEGORIES)
    bill = df[billing_mask].copy().reset_index(drop=True)
    print(f"billing/payments rows: {len(bill):,} of {len(df):,} "
          f"({100*len(bill)/max(len(df),1):.1f}%)")
    bill.to_parquet(out_billing, index=False)
    print(f"billing parquet written: {len(bill):,} rows -> {out_billing}")

    # ---- narrow dataset ----
    rec = to_col(df, "Record ID", "record_id")
    date = to_col(df, "Call_Date", "Start Time Date")
    month = to_col(df, "Call_Month")
    ncols = {
        "BAN": to_col(df, "BAN"),
        "record_id": rec,
        "Call_Date": date,
        "Call_Month": month,
        "Customer Intent Tag": to_col(df, "Customer Intent Tag"),
        "Problem Identified Tag": to_col(df, "Problem Identified Tag"),
        "Reason": to_col(df, "Reason"),
        "Summary": to_col(df, "Summary"),
        "Queue Category": to_col(df, "Queue Category"),
        "Conversation ID": to_col(df, "Conversation ID"),
        "QueueName": to_col(df, "QueueName"),
    }
    if any(v is None for v in ncols.values()):
        missing = [k for k, v in ncols.items() if v is None]
        raise SystemExit(f"raw parquet missing expected columns: {missing}")

    narrow = bill[[ncols[c] for c in NARROW_COLS]].copy()
    narrow.columns = NARROW_COLS
    # ensure identifiers / text are str
    for c in NARROW_COLS:
        if c not in {"Call_Date", "Call_Month"}:
            narrow[c] = narrow[c].fillna("").astype(str)
    narrow = narrow.astype(str)
    narrow.to_parquet(out_narrow, index=False)
    print(f"narrow billing/payments parquet written: {len(narrow):,} rows -> {out_narrow}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--raw", type=Path, default=OUT_DIR / "raw_all_string.parquet")
    ap.add_argument("--out-billing", type=Path, default=OUT_DIR / "billing_all.parquet")
    ap.add_argument("--out-narrow", type=Path, default=OUT_DIR / "billing_narrow.parquet")
    args = ap.parse_args()
    build_billing(args.raw, args.out_billing, args.out_narrow)


if __name__ == "__main__":
    main()
