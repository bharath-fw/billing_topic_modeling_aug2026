"""Data preparation: 7-month Brightspeed call data -> ML training dataset.

Reads the raw monthly ``*_All_Call_data.xlsx`` files under ``ytd_data/`` (streaming via
openpyxl read-only mode — full pandas xlsx load is far too slow for 600 MB files),
extracts the columns we care about, and writes one consolidated parquet "ML training
dataset" plus a per-month breakdown.

Output schema (the ML training dataset):
    ytd_call_id      : Call ID namespaced per month so it is unique across the YTD stack
    ban              : billing account number
    network_type     : network type (fiber / DSL / fixed wireless ...)
    record_id        : raw record id from the source
    month            : source file month (YYYY-MM)
    year_month       : actual call date truncated to YYYY-MM (from Start Time Date)
    call_date        : actual call date (Start Time Date), ISO yyyy-mm-dd
    category         : Category derived from Primary Call Reason (billing heuristic)
    call_intent      : Call Intent = collation of Root Cause + Reason (the text we model)
    text_unit        : alias of call_intent (used by the rest of the pipeline)
"""
from __future__ import annotations

import argparse
import re
import time
from pathlib import Path

import pandas as pd
from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[1]
YTD_DATA = ROOT / "ytd_data"
OUT_DIR = ROOT / "data"
OUT_PARQUET = OUT_DIR / "ytd_ml_dataset.parquet"

PLACEHOLDER = {
    "nan", "none", "na", "n/a", "-", "", "not clear",
    "not clear - transcript missing", "not clear - transcript not provided",
    "transcript not provided", "not provided", "transcript missing",
    "n/a - transcript not provided", "not applicable", "n/a", "no reason",
    "unknown", "not sure", "not specified",
}

MONTH_MAP = {
    "Jan": "2026-01", "Feb": "2026-02", "Mar": "2026-03", "Apr": "2026-04",
    "May": "2026-05", "June": "2026-06", "July": "2026-07", "Jul": "2026-07",
    "Aug": "2026-08",
}

KEEP_COLS = [
    "Call ID", "BAN", "Network Type", "Record ID",
    "Primary Call Reason", "Root Cause", "Reason", "Start Time Date",
]


def _month_from_filename(path: Path) -> str:
    for token in path.stem.split("_"):
        for key, val in MONTH_MAP.items():
            if token.startswith(key):
                return val
    raise ValueError(f"cannot infer month from {path.name}")


def clean_token(v) -> str:
    """Return a stripped token or '' when the value is a placeholder / empty."""
    if v is None:
        return ""
    t = str(v).strip()
    return "" if t.lower() in PLACEHOLDER else t


def build_intent(root_cause, reason) -> str:
    """Collation of Root Cause + Reason into a single call-intent string.

    The two columns are semantically overlapping free text that together express the
    customer's call intent.  We keep both (Root Cause first, Reason second), separated
    by a space so the sentence-transformer sees one short, natural string — no pipes or
    category prefixes that would leak the label we are trying to learn.
    """
    parts = [p for p in (clean_token(root_cause), clean_token(reason)) if p]
    return " ".join(parts)


def parse_date(v) -> tuple[str, str]:
    """Normalise Start Time Date -> (year_month YYYY-MM, call_date yyyy-mm-dd).

    Handles datetime objects, pandas Timestamps, Excel serial numbers and
    ISO-ish strings.  Returns ("", "") when unparseable.
    """
    if v is None or (isinstance(v, str) and not v.strip()):
        return "", ""
    try:
        if isinstance(v, (pd.Timestamp, pd.Timedelta)):
            ts = pd.Timestamp(v)
            return ts.strftime("%Y-%m"), ts.strftime("%Y-%m-%d")
        if isinstance(v, (int, float)) and v == v:  # Excel serial date (naive)
            ts = pd.Timestamp("1899-12-30") + pd.Timedelta(days=float(v))
            return ts.strftime("%Y-%m"), ts.strftime("%Y-%m-%d")
        s = str(v).strip()
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d",
                    "%m/%d/%Y %H:%M", "%m/%d/%Y", "%d-%b-%Y", "%Y/%m/%d"):
            try:
                ts = pd.Timestamp.strptime(s, fmt)
                return ts.strftime("%Y-%m"), ts.strftime("%Y-%m-%d")
            except ValueError:
                continue
        ts = pd.Timestamp(s)  # pandas flexible parser as last resort
        return ts.strftime("%Y-%m"), ts.strftime("%Y-%m-%d")
    except Exception:
        return "", ""


def extract_sheet(path: Path, sheet: str = "Data") -> pd.DataFrame:
    """Stream the target sheet into a DataFrame (read-only openpyxl)."""
    t0 = time.time()
    wb = load_workbook(path, read_only=True, data_only=True)
    if sheet not in wb.sheetnames:
        wb.close()
        raise ValueError(f"{path.name} has no '{sheet}' sheet: {wb.sheetnames}")
    ws = wb[sheet]
    it = ws.iter_rows(values_only=True)
    header = [str(h).strip() if h is not None else f"col{i}" for i, h in enumerate(next(it))]
    rows = [r for r in it]
    wb.close()
    df = pd.DataFrame(rows, columns=header)
    print(f"  {path.name}: {len(df):,} rows x {len(header)} cols "
          f"({time.time()-t0:.0f}s)")
    return df


def load_month(path: Path) -> pd.DataFrame:
    df = extract_sheet(path)
    month = _month_from_filename(path)
    col = {c: c for c in df.columns}
    def has(name):
        return next((k for k in df.columns if k == name), None)

    call_id_col = has("Call ID") or has("Conversation ID") or has("ConversationID")
    ban_col = has("BAN") or has("Ban")
    net_col = has("Network Type") or has("NetworkType")
    rec_col = has("Record ID") or has("RecordID") or has("RecordId")
    prim_col = has("Primary Call Reason") or has("PrimaryCallReason")
    root_col = has("Root Cause") or has("RootCause")
    reason_col = has("Reason")
    date_col = has("Start Time Date") or has("StartTimeDate")

    rename = [
        (call_id_col, "call_id"), (ban_col, "ban"), (net_col, "network_type"),
        (rec_col, "record_id"), (prim_col, "primary_call_reason"),
        (root_col, "root_cause"), (reason_col, "reason"), (date_col, "start_time_date"),
    ]
    keep, names = [], []
    for src, dst in rename:
        if src:
            keep.append(src)
            names.append(dst)
    df = df[keep].copy()
    df.columns = names
    df["month"] = month
    # YTD Call ID — namespaced to stay unique across months.  Call ID is often
    # missing; fall back to Record ID, then to a synthetic index-based id so
    # every row keeps a stable, unique identifier in the scoring output.
    cid = df["call_id"].fillna("").astype(str).str.strip()
    rid = df["record_id"].fillna("").astype(str).str.strip()
    idsrc = cid.where(cid.str.len() > 0, rid)
    empty = idsrc.str.len() == 0
    idsrc = idsrc.where(~empty, "r" + df.index.astype(str))
    df["ytd_call_id"] = month.replace("-", "") + "_" + idsrc
    # call intent = collation of Root Cause + Reason
    df["call_intent"] = [build_intent(r, s)
                         for r, s in zip(df["root_cause"], df["reason"])]
    df["text_unit"] = df["call_intent"]
    df["category"] = df["primary_call_reason"]  # heuristic Category from Primary Call Reason
    if date_col:
        dates = [parse_date(v) for v in df["start_time_date"]]
        df["year_month"] = [d[0] for d in dates]
        df["call_date"] = [d[1] for d in dates]
    else:
        df["year_month"] = ""
        df["call_date"] = ""
    for c in df.columns:
        if c not in {"call_intent", "text_unit"}:
            df[c] = df[c].astype(str)
    return df


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--months", nargs="*", default=None,
                    help="subset of filenames to process; default = all in ytd_data")
    ap.add_argument("--out", type=Path, default=OUT_PARQUET)
    args = ap.parse_args()

    files = sorted(YTD_DATA.glob("*.xlsx"))
    if args.months:
        files = [f for f in files if any(m.lower() in f.name.lower() for m in args.months)]
    if not files:
        raise SystemExit(f"no xlsx files found in {YTD_DATA}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    frames = []
    for f in files:
        frames.append(load_month(f))
    df = pd.concat(frames, ignore_index=True)
    df.to_parquet(args.out, index=False)
    print(f"\nML training dataset written: {len(df):,} rows -> {args.out}")
    print(df[["month", "category", "network_type", "ytd_call_id"]].head(5).to_string())


if __name__ == "__main__":
    main()