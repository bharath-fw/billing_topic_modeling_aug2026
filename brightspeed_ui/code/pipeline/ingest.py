"""Step 1: Concatenate all raw monthly Brightspeed xlsx into one str-dtyped parquet.

Reading the raw ``*_All_Call_Data.xlsx`` files from ``datasets/`` covers the full
scheduled year (Jan .. Aug 24, 2026).  Every column across every month is aligned
into a single union schema, and every value is coerced to ``str`` so the raw parquet
is unambiguous and downstream stages never trip over mixed dtypes.

Strategy
--------
* Each month is read with openpyxl in read-only/values mode (streaming — a full
  pandas xlsx load is far too slow / memory hungry for the multi-hundred-MB files).
* The union schema keeps ``<original>_…`` style naming when a few files spell a
  column differently, so no data is ever dropped.
* All columns are cast to ``str`` and empty/placeholder cells become ``""``.
* The ``Source`` column records which monthly file (month tag) each row came from.
* ``Start Time Date`` is kept as a string in the raw parquet; a parsed ISO date /
  month is added as ``Call_Date`` / ``Call_Month`` for downstream convenience.
"""
from __future__ import annotations

import argparse
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "datasets"
OUT_DIR = ROOT / "code" / "data"

DATE_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d",
                "%m/%d/%Y %H:%M", "%m/%d/%Y")


def _str(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v != v:          # NaN
        return ""
    if isinstance(v, str):
        return v.strip()
    return str(v)


def _parse_date_cell(v):
    """Best-effort conversion of the Start Time Date cell -> (ISO date, YYYY-MM)."""
    if v is None:
        return "", ""
    try:
        if isinstance(v, datetime):
            ts = v
        elif isinstance(v, pd.Timestamp):
            ts = v.to_pydatetime()
        elif isinstance(v, (int, float)) and v == v:
            ts = pd.Timestamp("1899-12-30") + pd.Timedelta(days=float(v))
            ts = ts.to_pydatetime()
        else:
            s = str(v).strip()
            if not s:
                return "", ""
            for fmt in DATE_FORMATS:
                try:
                    ts = datetime.strptime(s, fmt)
                    break
                except ValueError:
                    continue
            else:
                ts = pd.Timestamp(s).to_pydatetime()
        return ts.strftime("%Y-%m-%d"), ts.strftime("%Y-%m")
    except Exception:
        return "", ""


def read_month(path: Path) -> pd.DataFrame:
    wb = load_workbook(path, read_only=True, data_only=True)
    sheet = "Data" if "Data" in wb.sheetnames else wb.sheetnames[0]
    ws = wb[sheet]
    it = ws.iter_rows(values_only=True)
    header = [_str(h) or f"col{i}" for i, h in enumerate(next(it))]
    # de-duplicate repeated header names
    seen: dict[str, int] = {}
    clean = []
    for h in header:
        if h in seen:
            seen[h] += 1
            clean.append(f"{h}__{seen[h]}")
        else:
            seen[h] = 0
            clean.append(h)
    header = clean
    rows = [list(r) for r in it]
    wb.close()

    df = pd.DataFrame(rows, columns=header)
    df = df.map(_str)
    # drop accidental Excel artifact columns (e.g. a leaked "=MIN(...)" cell that
    # openpyxl materialises as a stray numeric header)
    df = df.loc[:, ~df.columns.astype(str).str.startswith("=")]

    date_col = next((c for c in header if c.lower().replace(" ", "") in
                     {"starttimedate", "starttime date", "start_time_date"}), None)
    if date_col:
        parsed = df[date_col].map(_parse_date_cell)
        df["Call_Date"] = [d for d, _ in parsed]
        df["Call_Month"] = [m for _, m in parsed]
    else:
        df["Call_Date"] = ""
        df["Call_Month"] = ""
    return df


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=OUT_DIR / "raw_all_string.parquet")
    ap.add_argument("--months", nargs="*", default=None,
                    help="optional subset of filenames to include")
    args = ap.parse_args()

    files = sorted(DATA_DIR.glob("*.xlsx"))
    if args.months:
        files = [f for f in files if any(m.lower() in f.name.lower() for m in args.months)]
    if not files:
        raise SystemExit(f"no xlsx files found in {DATA_DIR}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    frames = []
    for f in files:
        t0 = time.time()
        df = read_month(f)
        df.insert(0, "Source", f.stem)
        frames.append(df)
        print(f"  {f.name}: {len(df):,} rows x {df.shape[1]} cols ({time.time()-t0:.0f}s)")
        del df

    combined = pd.concat(frames, ignore_index=True, sort=False)
    # every column string dtype
    combined = combined.astype(str)
    combined.to_parquet(args.out, index=False)
    print(f"\nraw all-string parquet written: {len(combined):,} rows x "
          f"{combined.shape[1]} cols -> {args.out}")


if __name__ == "__main__":
    main()
