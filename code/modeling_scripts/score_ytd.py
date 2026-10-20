"""Full-scale inference: score every billing line of the 7-month YTD data.

Reuses the cached billing kernel + GLVQ to produce the final single scoring file:

  outputs/scoring_ytd_billing.xlsx

with columns:
  ytd_call_id, call_intent, billing_related, call_date, year_month, ban,
  network_type, record_id, category (heuristic), billing_prob,
  category_1..3, subcategory_1..3, conf_1..3

Run after ``build_taxonomy.py`` (needs artifacts/billing_kernel.joblib,
artifacts/glvq.joblib, artifacts/glvq_active_keys.json).

  python scripts/score_ytd.py                 # all months (embeds ~all rows)
  python scripts/score_ytd.py --months Jan Feb # subset
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import pipeline as P  # noqa: E402
from src.billing_kernel import BillingKernel  # noqa: E402
from src.config import ARTIFACTS_DIR, CACHE_DIR, OUTPUTS_DIR  # noqa: E402
from src.embed import embed_cached  # noqa: E402
from src.lvq import GLVQ  # noqa: E402

BATCH = 8192


def score_full(df: pd.DataFrame, kernel: BillingKernel, model: GLVQ,
               active_keys: list[str], months: list[str] | None = None,
               out: Path = OUTPUTS_DIR / "scoring_ytd_billing.xlsx") -> Path:
    """Embed + score all rows (or a month subset), write XLSX."""
    if months:
        df = df[df["month"].isin(months)]
    t0 = time.time()
    texts = df["text_unit"].tolist()

    # ---------- stage A: billing probability for every row ----------
    emb_all = embed_cached(pd.Series(texts), "ytd_all_emb")
    proba = kernel.predict(emb_all)
    billing_mask = proba >= kernel.threshold
    print(f"[{pd.Timestamp.now():%H:%M:%S}] billing rows: {int(billing_mask.sum()):,} "
          f"of {len(df):,} ({(time.time()-t0)/60:.1f} min to embed)")

    # ---------- stage B: top-3 category/subcategory on billing rows ----------
    Xb = emb_all[billing_mask]
    score_df = P.score_topk(model, Xb, active_keys, k=3)
    bill_rows = df[billing_mask].reset_index(drop=True)

    out_df = bill_rows[["ytd_call_id", "call_intent", "call_date", "year_month",
                        "ban", "network_type", "record_id", "category",
                        "month"]].copy()
    out_df.insert(2, "billing_related", 1)
    out_df["billing_prob"] = np.round(proba[billing_mask], 4)
    out_df = pd.concat([out_df.reset_index(drop=True),
                        score_df.reset_index(drop=True)], axis=1)

    with pd.ExcelWriter(out, engine="openpyxl") as xw:
        out_df.to_excel(xw, sheet_name="Billing_Scoring", index=False)
        pd.DataFrame([kernel.metrics]).T.to_excel(xw, sheet_name="Model_Metrics")
        pd.DataFrame({
            "n_total": [len(df)], "n_billing": [int(billing_mask.sum())],
            "billing_share": [float(billing_mask.mean())],
        }).to_excel(xw, sheet_name="Summary")
    print(f"scoring file written: {out} ({len(out_df):,} rows, "
          f"{(time.time()-t0)/60:.1f} min)")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--months", nargs="*", default=None)
    args = ap.parse_args()

    df = P.load_ml_dataset()
    kernel = BillingKernel.load(ARTIFACTS_DIR / "billing_kernel.joblib")
    model = GLVQ.load(ARTIFACTS_DIR / "glvq.joblib")
    active = json.loads((ARTIFACTS_DIR / "glvq_active_keys.json").read_text())
    score_full(df, kernel, model, active["active_keys"], args.months)


if __name__ == "__main__":
    main()