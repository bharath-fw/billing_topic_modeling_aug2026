"""Export the mined taxonomy to an Excel sheet (for the ChatGPT plugin + humans).

  python scripts/export_taxonomy_to_xlsx.py

Writes outputs/taxonomy_mined.xlsx with one sheet per category (Category,
Subcategory, Keywords, Representative text, Call volume, Share) plus an
"All_Leaves" flat sheet.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import DATA_DIR, OUTPUTS_DIR  # noqa: E402

OUT = OUTPUTS_DIR / "taxonomy_mined.xlsx"


def main() -> None:
    mined = json.loads((DATA_DIR / "taxonomy_mined.json").read_text())
    with pd.ExcelWriter(OUT, engine="openpyxl") as xw:
        rows = []
        for cat in mined["categories"]:
            df = pd.DataFrame(cat["subcategories"])
            df.insert(0, "category", cat["name"])
            df = df[["category", "name", "keywords", "rep", "count"]]
            df.columns = ["Category", "Subcategory", "Keywords", "Representative", "Calls"]
            df.to_excel(xw, sheet_name=_sn(cat["name"]), index=False)
            rows.append(df)
        flat = pd.concat(rows, ignore_index=True)
        flat["share_%"] = (flat["Calls"] / mined["meta"]["n_rows"] * 100).round(3)
        flat.to_excel(xw, sheet_name="All_Leaves", index=False)
    print(f"taxonomy exported -> {OUT}")


def _sn(name: str, maxlen: int = 31) -> str:
    return "".join(c if c.isalnum() else "_" for c in name)[:maxlen] or "Cat"


if __name__ == "__main__":
    main()